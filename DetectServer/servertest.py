from flask import Flask, request, jsonify

app = Flask(__name__)


@app.route('/api/endpoint', methods=['POST'])
def handle_post_request():
    # 检查请求中是否包含 JSON 数据
    if request.is_json:
        # 获取 JSON 数据
        data = request.get_json()

        # 打印接收到的 JSON 数据
        print("Received JSON data:")
        print(data)

        # 返回响应
        return jsonify({"status": "success", "received": data}), 200
    else:
        return jsonify({"status": "error", "message": "Request must be JSON"}), 400


if __name__ == '__main__':
    # 运行 Flask 应用
    app.run(debug=True, host='0.0.0.0', port=5000)