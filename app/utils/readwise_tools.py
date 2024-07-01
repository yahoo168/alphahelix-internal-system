from .mongodb_tools import MDB_client
from alphahelix_database_tools.external_tools import readwise_tools

# 建立readwise client，先配置MDB_client，用戶toekn在routes中，依照用戶別再配置
readwise_client = readwise_tools.ReadwiseTool(MDB_client=MDB_client, token=None)