from pymongo import MongoClient
from .utils import *

username = "yahoo168"
password = "yahoo210"

articles_cluster_uri = f"mongodb+srv://{username}:{password}@articles.zlnaiap.mongodb.net/?retryWrites=true&w=majority&appName=articles"
MDB_client = MongoClient(articles_cluster_uri)