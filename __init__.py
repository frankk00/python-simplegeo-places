from _version import __version__

API_VERSION = '1.0'

from httplib2 import Http
import oauth2 as oauth
from urlparse import urljoin
import time

from jsonutil import jsonutil as json

def json_decode(jsonstr):
    try: 
        return json.loads(jsonstr)
    except (ValueError, TypeError), le:
        raise DecodeError(jsonstr, le)

class Client(object):
    realm = "http://api.simplegeo.com"
    endpoints = {
        'endpoints': 'endpoints.json',
        'places': 'places/%(simplegeoid)s.json',
        'place': 'places/place.json',
        'search': 'places/%(lat)s,%(lon)s/search.json?q=%(query)s&category=%(category)s',
    }

    def __init__(self, key, secret, api_version=API_VERSION, host="api.simplegeo.com", port=80):
        self.host = host
        self.port = port
        self.consumer = oauth.Consumer(key, secret)
        self.key = key
        self.secret = secret
        self.api_version = api_version
        self.signature = oauth.SignatureMethod_HMAC_SHA1()
        self.uri = "http://%s:%s" % (host, port)
        self.http = Http()

    def get_endpoint_descriptions(self):
        result = self._request(self.endpoint('endpoints'), 'GET')
        return json.loads(result)

    def endpoint(self, name, **kwargs):
        try:
            endpoint = self.endpoints[name]
        except KeyError:
            raise Exception('No endpoint named "%s"' % name)
        try:
            endpoint = endpoint % kwargs
        except KeyError, e:
            raise TypeError('Missing required argument "%s"' % (e.args[0],))
        return urljoin(urljoin(self.uri, self.api_version + '/'), endpoint)

    def add_record(self, record):
        endpoint = self.endpoint('place')
        self._request(endpoint, "PUT", record.to_json())

    def get_record(self, simplegeoid):
        endpoint = self.endpoint('places', simplegeoid=simplegeoid)
        result = self._request(endpoint, 'GET')
        return Record.from_json(result)

    def update_record(self, record):
        endpoint = self.endpoint('places', simplegeoid=record.id)
        return self._request(endpoint, 'POST', record.to_json())

    def delete_record(self, simplegeoid):
        endpoint = self.endpoint('places', simplegeoid=simplegeoid)
        return self._request(endpoint, 'DELETE')

    def search(self, lat, lon, query='', category=''):
        endpoint = self.endpoint('search', lat=lat, lon=lon, query=query, category=category)
        result = self._request(endpoint, 'GET')
        
        fc = json_decode(result)
        return set(Record.from_dict(f) for f in fc['features'])

    def _request(self, endpoint, method, data=None):
        if data is not None and not isinstance(data, basestring):
             raise TypeError("data is required to be None or a string or unicode, not %s" % (type(data),))
        params = {}
        body = data
        request = oauth.Request.from_consumer_and_token(self.consumer,
            http_method=method, http_url=endpoint, parameters=params)

        request.sign_request(self.signature, self.consumer, None)
        headers = request.to_header(self.realm)
        headers['User-Agent'] = 'SimpleGeo Places Client v%s' % __version__

        resp, content = self.http.request(endpoint, method, body=body, headers=headers)

        if resp['status'][0] not in ('2', '3'):
            raise APIError(int(resp['status']), content, resp)

        return content

class Record:
    def __init__(self, id, lat, lon, type='object', created=None, **kwargs):
        self.id = id
        self.lon = lon
        self.lat = lat
        self.type = type
        if created is None:
            self.created = int(time.time())
        else:
            self.created = created
        self.__dict__.update(kwargs)

    @classmethod
    def from_dict(cls, data):
        assert data
        coord = data['geometry']['coordinates']
        record = cls(data['id'], lat=coord[1], lon=coord[0])
        record.type = data['properties']['type']
        record.created = data.get('created', record.created)
        record.__dict__.update(dict((k, v) for k, v in data['properties'].iteritems()
                                    if k not in ('type', 'created')))
        return record

    def to_dict(self):
        return {
            'type': 'Feature',
            'id': self.id,
            'created': self.created,
            'geometry': {
                'type': 'Point',
                'coordinates': [self.lon, self.lat],
            },
            'properties': dict((k, v) for k, v in self.__dict__.iteritems() 
                                        if k not in ('lon', 'lat', 'id', 'created')),
        }

    @classmethod
    def from_json(cls, jsonstr):
        return cls.from_dict(json_decode(jsonstr))

    def to_json(self):
        return json.dumps(self.to_dict())


class APIError(Exception):
    """Base exception for all API errors."""

    def __init__(self, code, msg, headers, description=''):
        self.code = code
        self.msg = msg
        self.headers = headers
        self.description = description

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return "%s (#%s) %s" % (self.msg, self.code, self.description)

class DecodeError(APIError):
    """There was a problem decoding the API's JSON response."""

    def __init__(self, body, le):
        super(DecodeError, self).__init__(None, "Could not decode JSON", None, repr(le))
        self.body = body

    def __repr__(self):
        return "%s content: %s" % (self.description, self.body)

