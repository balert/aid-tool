import requests, json, logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class AID():
    def __init__(self, tenant, user, pw):
        self.session_file = tenant + ".json"
        self.base_url = "https://www.aircraft-info.de/" + tenant
        self.user = user
        self.pw = pw
        try:
            with open(self.session_file) as f:
                session = json.load(f)
            self.cookies = session["cookies"]
        except Exception as e:
            self.cookies = {}
        self.login()

    def save_session(self):
        with open(self.session_file, 'w') as f:
            f.write(json.dumps({"cookies": self.cookies}))


    def login(self):
        # test if login required
        r = requests.get("%s/dashboards/mydashboard.php" % self.base_url, cookies=self.cookies)
        self.cookies = r.cookies.get_dict()
        soup = BeautifulSoup(r.text, 'html.parser')
        if not "Login Page" in str(soup.title):
            logger.debug('Login not required')
            return

        # GET login form
        r = requests.get("%s/site_login.php" % self.base_url, cookies=self.cookies)
        self.cookies = r.cookies.get_dict()
        soup = BeautifulSoup(r.text, 'html.parser')
        loginform = soup.find("form")
        _csrf_token = loginform.find("input", {"type": "hidden", "name": "_csrf_token"})["value"]

        # craft login POST request
        login_url = "%s/site_logon.php" % self.base_url

        data = {
            '_csrf_token': _csrf_token,
            '_redirparms': '',
            '_auswahl': '',
            '_login': self.user,
            '_pass': self.pw
        }

        r = requests.post(login_url, data=data, cookies=self.cookies)
        self.cookies = r.cookies.get_dict()
        self.save_session()

    def get_flightlog(self, since, until):
        req_url="%s/mydata/flightlog_exec.php?_since_date=%s&_until_date=%s" % (self.base_url, since, until) 
        r = requests.get(req_url, cookies=self.cookies)
        assert(r.status_code == 200)
        ret = json.loads(r.text)
        return ret
        