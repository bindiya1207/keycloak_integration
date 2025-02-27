from keycloak import KeycloakOpenID

keycloak_openid = KeycloakOpenID(
    server_url="http://localhost:8080",
    client_id='8afea2b4-ce8f-457c-bfe2-a70fcb161dff',  # Replace with Azure client ID
    realm_name="myrealm",
    client_secret_key='F9S4WNHQRgtgmcq1upnJGpvZKRLlIqj3'  # Replace with Keycloak client secret
)

REDIRECT_URI = "http://localhost:5000/callback"  # Same as Keycloak client redirect URI