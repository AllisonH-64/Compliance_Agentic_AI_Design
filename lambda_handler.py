"""Lambda entry point. Wraps the existing FastAPI app (unmodified) with Mangum so it
runs as a Lambdalith behind API Gateway HTTP API. See infra/api_stack.py."""

from mangum import Mangum

from app.main import app

handler = Mangum(app)
