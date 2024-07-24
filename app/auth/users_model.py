# app/models.py
from flask import current_app as app
from flask_login import UserMixin
from bson import ObjectId
from app.utils.mongodb_tools import MDB_client
#from flask_principal import RoleNeed, UserNeed, Identity, identity_changed, identity_loaded, AnonymousIdentity

def load_user(user_id):
    return User.get(user_id)

class User(UserMixin):
    def __init__(self, employee_id, username, email, password_hash, roles, _id=None):
        self.employee_id = employee_id
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.roles = roles
        self._id = _id

    # 调用静态方法，不需要实例化类
    @staticmethod
    def get(user_id):
        try:
            user_data_dict = MDB_client["users"]["user_basic_info"].find_one({"_id": ObjectId(user_id)})
            return User(employee_id=user_data_dict["employee_id"], username=user_data_dict['username'], 
                        email=user_data_dict['email'], password_hash=user_data_dict['password_hash'],
                        _id=user_data_dict['_id'], roles=user_data_dict['roles'],)
        except:
            return None

    # 在 Flask-Login 中，用户模型必须实现get_id以便在框架中自動調用，例如user_loader以及current_user
    def get_id(self):
        return str(self._id)

def check_username_exist(username):
    if MDB_client["users"]["user_basic_info"].find_one({"username": username}):
        return True
    else:
        return False

def create_new_user(email, username, password_hash, roles):
    user_basic_info = {
        "email": email,
        "username": username,
        "password_hash": password_hash,
        "roles": roles,
        "send_report_to_email": True,
        "is_active": True,
        # 待改
        "employee_id": None,
    }
    MDB_client["users"]["user_basic_info"].insert_one(user_basic_info)