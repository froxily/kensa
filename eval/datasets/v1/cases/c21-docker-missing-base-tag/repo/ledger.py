from http.server import BaseHTTPRequestHandler, HTTPServer

class LedgerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ready")

if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8080), LedgerHandler).serve_forever()
