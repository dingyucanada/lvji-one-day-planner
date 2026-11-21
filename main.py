"""旅迹 LVJI · 入口兼容层（托管平台按 python main.py 启动）"""
import os
from http.server import ThreadingHTTPServer

import server

if __name__ == '__main__':
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 8000))
    print('旅迹 LVJI 一日行程运行于 http://%s:%d' % (host, port), flush=True)
    ThreadingHTTPServer((host, port), server.Handler).serve_forever()
