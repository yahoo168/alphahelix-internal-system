from app import create_app
import os
import base64

# 處理GCS的金鑰（因heroku無法儲存json檔，只能儲存base64編碼後的字串，故於此解碼）
# 從環境變量中獲取 base64 編碼字串
encoded_key = os.environ['GOOGLE_APPLICATION_CREDENTIALS_JSON']
# 解碼 base64 字串
decoded_key = base64.b64decode(encoded_key)
# 將解碼後的內容寫入臨時檔案
temp_gcp_key_path = '/tmp/gcp_key.json'
with open(temp_gcp_key_path, 'wb') as temp_file:
    temp_file.write(decoded_key)
# 設置 GOOGLE_APPLICATION_CREDENTIALS 環境變量指向臨時檔案
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = temp_gcp_key_path

app = create_app()
#把app context推入stack中，擴張到整個應用
app.app_context().push()

if __name__ == '__main__':
    app.run(debug=True)