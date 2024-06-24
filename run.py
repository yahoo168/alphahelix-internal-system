from app import create_app

app = create_app()
#把app context推入stack中，擴張到整個應用
app.app_context().push()

if __name__ == '__main__':
    app.run(debug=True)