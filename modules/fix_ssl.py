import os
import sys

def fix_anaconda_ssl():
    # 彻底清除干扰 SSL 的环境变量
    faulty_vars = ["SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"]
    for var in faulty_vars:
        if var in os.environ:
            # print(f"DEBUG: Removing {var}={os.environ[var]}")
            del os.environ[var]

fix_anaconda_ssl()
