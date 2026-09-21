"""Create only this environment's new test database through Odoo's create API."""
import os

import odoo
from odoo.service import db
from odoo.tools import config

config.parse_config(["-c", "/etc/odoo16c.conf"])
assert config["db_host"] == "db"
assert config["db_user"] == "odoo16c"
assert config["db_name"] == "odoo16c_test"
config["list_db"] = True
odoo.netsvc.init_logger()
odoo.modules.module.initialize_sys_path()
if "odoo16c_test" in db.list_dbs(force=True):
    raise SystemExit("Test database already exists; initialization refused.")
db.exp_create_database(
    "odoo16c_test", False, "zh_TW", os.environ["TEST_ADMIN_PASSWORD"],
    login="admin", country_code="TW",
)
print("Created independent test database odoo16c_test.")
