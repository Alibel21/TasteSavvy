import json, re, os, time, urllib.request, urllib.error
from http.server import SimpleHTTPRequestHandler, HTTPServer

os.chdir(os.path.dirname(os.path.abspath(__file__)))
URL = "https://maas-api.antdigital.com/v1/chat/completions"


def cfg():
    return json.load(open("config.json", encoding="utf-8"))


def call_model(payload, key):
    """调用模型。遇到 429（限流）自动重试，最多再试 2 次，间隔 3 秒、6 秒。"""
    data = json.dumps(payload).encode("utf-8")
    for attempt in range(3):
        req = urllib.request.Request(
            URL, data, {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")
            print(f"[接口返回 {e.code}] 第 {attempt + 1} 次：{body[:300]}")
            if e.code == 429 and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            hint = "（平台限流，请稍后再试）" if e.code == 429 else ""
            raise RuntimeError(f"接口返回 {e.code}{hint}：{body[:200]}")


class H(SimpleHTTPRequestHandler):
    def do_GET(self):
        # 只开放网页本身，避免 config.json（含 Key）被访问
        if self.path in ("/", "/canteen.html"):
            self.path = "/canteen.html"
            return super().do_GET()
        self.send_error(404)

    def do_POST(self):
        if self.path != "/api/recognize":
            return self.send_error(404)
        n = int(self.headers.get("Content-Length", 0))
        out = self.recognize(json.loads(self.rfile.read(n)))
        b = json.dumps(out, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def recognize(self, body):
        try:
            c = cfg()
            wl = "\n".join(f"{w['id']}: {w['name']}" for w in body["windows"])
            prompt = (
                "这是一张食堂窗口的照片。候选窗口列表（编号: 名称）：\n" + wl +
                "\n请读出照片中的窗口号和文字名称，并从候选列表中选出最匹配的至多3个窗口编号。"
                "如果招牌文字看不清，read_text 填空字符串。"
                '只返回JSON，格式：{"read_text":"你读到的文字","candidates":["编号1","编号2"]}'
            )
            payload = {
                "model": c["model"],
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": body["image"]}},
                ]}],
            }
            resp = call_model(payload, c["api_key"])
            text = str(resp["choices"][0]["message"]["content"])
            print("[模型原始回复]", text[:300])
            m = re.search(r"\{.*\}", text, re.S)
            if m:
                try:
                    return json.loads(m.group(0))
                except ValueError:
                    pass
            # 模型没按格式返回时，把原文交给网页，由网页自己匹配窗口名
            return {"read_text": text[:80], "candidates": []}
        except Exception as e:
            return {"error": str(e)}


if __name__ == "__main__":
    print("已启动，请在浏览器打开 http://localhost:8000")
    HTTPServer(("127.0.0.1", 8000), H).serve_forever()
