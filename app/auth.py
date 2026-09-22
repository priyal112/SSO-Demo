import os
from dotenv import load_dotenv

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

# Authlib handles the OAuth/OIDC communication
from authlib.integrations.starlette_client import OAuth


# Read values from the .env file
load_dotenv()

# endpoints
router = APIRouter(prefix="/auth")


# OAuth client
oauth = OAuth()

# Register Auth0 as our identity provider
oauth.register(
    name="auth0",
    client_id=os.getenv("AUTH0_CLIENT_ID"),
    client_secret=os.getenv("AUTH0_CLIENT_SECRET"),
    server_metadata_url=f"https://{os.getenv('AUTH0_DOMAIN')}/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid profile email",
    },
)


# login process
@router.get("/login")
async def login(request: Request):

    # Build the callback URL registered in Auth0
    redirect_uri = os.getenv("AUTH0_CALLBACK_URL")

    # Redirect the user to Auth0
    return await oauth.auth0.authorize_redirect(
        request,
        redirect_uri,
    )


@router.get("/callback")
async def callback(request: Request):

    # Exchange the code for tokens
    token = await oauth.auth0.authorize_access_token(request)

    # Get authenticated user information
    user = token.get("userinfo")

    request.session["user"] = user

    # Redirect the user back to the frontend
    #return RedirectResponse(
    #url=os.getenv("FRONTEND_DASHBOARD_URL"),
    #status_code=302,)

    # Return a backend response
    return {
        "message": "SSO login successful",
        "user": user,
    }


@router.get("/me")
async def get_current_user(request: Request):

    # Read the logged-in user from the session
    user = request.session.get("user")

    if not user:
        return {"message": "Not authenticated"}

    return {
        "message": "Authenticated user",
        "user": user,
    }


@router.get("/logout")
async def logout(request: Request):

    # Remove the logged-in user from the session
    request.session.clear()

    # Send the user back to the frontend
    return RedirectResponse(
        url=os.getenv("FRONTEND_URL"),
        status_code=302,
    )



