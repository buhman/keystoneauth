# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from positional import positional

from keystoneauth1 import access
from keystoneauth1.identity.v3 import federation

__all__ = ('OidcAuthorizationCode',
           'OidcPassword')


class _OidcBase(federation.FederationBaseAuth):
    """Base class for different OpenID Connect based flows.

    The OpenID Connect specification can be found at::
    ``http://openid.net/specs/openid-connect-core-1_0.html``
    """

    def __init__(self, auth_url, identity_provider, protocol,
                 client_id, client_secret, access_token_endpoint,
                 grant_type, access_token_type, **kwargs):
        """The OpenID Connect plugin expects the following.

        :param auth_url: URL of the Identity Service
        :type auth_url: string

        :param identity_provider: Name of the Identity Provider the client
                                  will authenticate against
        :type identity_provider: string

        :param protocol: Protocol name as configured in keystone
        :type protocol: string

        :param client_id: OAuth 2.0 Client ID
        :type client_id: string

        :param client_secret: OAuth 2.0 Client Secret
        :type client_secret: string

        :param access_token_endpoint: OpenID Connect Provider Token Endpoint,
                                      for example:
                                      https://localhost:8020/oidc/OP/token
        :type access_token_endpoint: string

        :param grant_type: OpenID Connect grant type, it represents the flow
                           that is used to talk to the OP. Valid values are:
                           "authorization_code", "refresh_token", or
                           "password".
        :type grant_type: string

        :param access_token_type: OAuth 2.0 Authorization Server Introspection
                                  token type, it is used to decide which type
                                  of token will be used when processing token
                                  introspection. Valid values are:
                                  "access_token" or "id_token"
        :type access_token_type: string

        """
        super(_OidcBase, self).__init__(auth_url, identity_provider, protocol,
                                        **kwargs)
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token_endpoint = access_token_endpoint
        self.grant_type = grant_type
        self.access_token_type = access_token_type

    def _get_access_token(self, session, client_auth, payload):
        """Exchange a variety of user supplied values for an access token.

        :param session: a session object to send out HTTP requests.
        :type session: keystoneauth1.session.Session

        :param client_auth: a tuple representing client id and secret
        :type client_auth: tuple

        :param payload: a dict containing various OpenID Connect values, for
                        example::
                          {'grant_type': 'password', 'username': self.username,
                           'password': self.password, 'scope': self.scope}
        :type payload: dict
        """
        op_response = session.post(self.access_token_endpoint,
                                   requests_auth=client_auth,
                                   data=payload,
                                   authenticated=False)
        return op_response

    def _get_keystone_token(self, session, access_token):
        r"""Exchange an acess token for a keystone token.

        By Sending the access token in an `Authorization: Bearer` header, to
        an OpenID Connect protected endpoint (Federated Token URL). The
        OpenID Connect server will use the access token to look up information
        about the authenticated user (this technique is called instrospection).
        The output of the instrospection will be an OpenID Connect Claim, that
        will be used against the mapping engine. Should the mapping engine
        succeed, a Keystone token will be presented to the user.

        :param session: a session object to send out HTTP requests.
        :type session: keystoneauth1.session.Session

        :param access_token: The OpenID Connect access token.
        :type access_token: str
        """
        # use access token against protected URL
        headers = {'Authorization': 'Bearer ' + access_token}
        auth_response = session.post(self.federated_token_url,
                                     headers=headers,
                                     authenticated=False)
        return auth_response


class OidcPassword(_OidcBase):
    """Implementation for OpenID Connect Resource Owner Password Credential."""

    @positional(4)
    def __init__(self, auth_url, identity_provider, protocol,
                 client_id, client_secret, access_token_endpoint,
                 grant_type='password', access_token_type='access_token',
                 username=None, password=None, scope='profile'):
        """The OpenID Password plugin expects the following.

        :param username: Username used to authenticate
        :type username: string

        :param password: Password used to authenticate
        :type password: string

        :param scope: OpenID Connect scope that is requested from OP,
                      defaults to "profile", for example: "profile email"
        :type scope: string

        """
        super(OidcPassword, self).__init__(
            auth_url=auth_url,
            identity_provider=identity_provider,
            protocol=protocol,
            client_id=client_id,
            client_secret=client_secret,
            access_token_endpoint=access_token_endpoint,
            grant_type=grant_type,
            access_token_type=access_token_type)
        self.username = username
        self.password = password
        self.scope = scope

    def get_unscoped_auth_ref(self, session):
        """Authenticate with OpenID Connect and get back claims.

        This is a multi-step process. First an access token must be retrieved,
        to do this, the username and password, the OpenID Connect client ID
        and secret, and the access token endpoint must be known.

        Secondly, we then exchange the access token upon accessing the
        protected Keystone endpoint (federated auth URL). This will trigger
        the OpenID Connect Provider to perform a user introspection and
        retrieve information (specified in the scope) about the user in
        the form of an OpenID Connect Claim. These claims will be sent
        to Keystone in the form of environment variables.

        :param session: a session object to send out HTTP requests.
        :type session: keystoneauth1.session.Session

        :returns: a token data representation
        :rtype: :py:class:`keystoneauth1.access.AccessInfoV3`
        """
        # get an access token
        client_auth = (self.client_id, self.client_secret)
        payload = {'grant_type': self.grant_type, 'username': self.username,
                   'password': self.password, 'scope': self.scope}
        response = self._get_access_token(session, client_auth, payload)
        access_token = response.json()[self.access_token_type]

        response = self._get_keystone_token(session, access_token)

        # grab the unscoped token
        return access.create(resp=response)


class OidcAuthorizationCode(_OidcBase):
    """Implementation for OpenID Connect Authorization Code."""

    @positional(4)
    def __init__(self, auth_url, identity_provider, protocol,
                 client_id, client_secret, access_token_endpoint,
                 grant_type='authorization_code',
                 access_token_type='access_token',
                 redirect_uri=None, code=None):
        """The OpenID Authorization Code plugin expects the following.

        :param redirect_uri: OpenID Connect Client Redirect URL
        :type redirect_uri: string

        :param code: OAuth 2.0 Authorization Code
        :type code: string

        """
        super(OidcAuthorizationCode, self).__init__(
            auth_url=auth_url,
            identity_provider=identity_provider,
            protocol=protocol,
            client_id=client_id,
            client_secret=client_secret,
            access_token_endpoint=access_token_endpoint,
            grant_type=grant_type,
            access_token_type=access_token_type)
        self.redirect_uri = redirect_uri
        self.code = code

    def get_unscoped_auth_ref(self, session):
        """Authenticate with OpenID Connect and get back claims.

        This is a multi-step process. First an access token must be retrieved,
        to do this, an authorization code and redirect URL must be given.

        Secondly, we then exchange the access token upon accessing the
        protected Keystone endpoint (federated auth URL). This will trigger
        the OpenID Connect Provider to perform a user introspection and
        retrieve information (specified in the scope) about the user in
        the form of an OpenID Connect Claim. These claims will be sent
        to Keystone in the form of environment variables.

        :param session: a session object to send out HTTP requests.
        :type session: keystoneauth1.session.Session

        :returns: a token data representation
        :rtype: :py:class:`keystoneauth1.access.AccessInfoV3`
        """
        # get an access token
        client_auth = (self.client_id, self.client_secret)
        payload = {'grant_type': self.grant_type,
                   'redirect_uri': self.redirect_uri,
                   'code': self.code}
        response = self._get_access_token(session, client_auth, payload)
        access_token = response.json()[self.access_token_type]

        response = self._get_keystone_token(session, access_token)

        # grab the unscoped token
        return access.create(resp=response)
