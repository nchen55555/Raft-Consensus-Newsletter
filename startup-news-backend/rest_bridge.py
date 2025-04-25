from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import List, Optional
import grpc

from protos import blog_pb2, blog_pb2_grpc
from server import find_leader_stub

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SubscribeRequest(BaseModel):
    email: EmailStr

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class CreateAccountRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

class CreatePostRequest(BaseModel):
    title: str
    content: str
    author: str

class Post(BaseModel):
    post_id: str
    author: str
    title: str
    content: str
    timestamp: str
    likes: int

@app.post("/api/subscribe")
def subscribe(req: SubscribeRequest):
    stub = find_leader_stub()
    if not stub:
        raise HTTPException(status_code=503, detail="Leader not available")

    grpc_req = blog_pb2.Request(info=[req.email])
    grpc_resp = stub.RPCSubscribe(grpc_req)

    if grpc_resp.operation == blog_pb2.SUCCESS:
        return { "success": True }
    return { "success": False, "error": grpc_resp.info[0] if grpc_resp.info else "Unknown error" }

@app.post("/api/login")
def login(req: LoginRequest):
    stub = find_leader_stub()
    if not stub:
        raise HTTPException(status_code=503, detail="Leader not available")

    grpc_req = blog_pb2.Request(info=[req.email, req.password])
    grpc_resp = stub.RPCLogin(grpc_req)

    if grpc_resp.operation == blog_pb2.SUCCESS:
        return { "success": True }
    return { "success": False, "error": grpc_resp.info[0] if grpc_resp.info else "Invalid credentials" }

@app.post("/api/create-account")
def create_account(req: CreateAccountRequest):
    stub = find_leader_stub()
    if not stub:
        raise HTTPException(status_code=503, detail="Leader not available")

    grpc_req = blog_pb2.Request(info=[req.name, req.email, req.password])
    grpc_resp = stub.RPCCreateAccount(grpc_req)

    if grpc_resp.operation == blog_pb2.SUCCESS:
        return { "success": True }
    return { "success": False, "error": grpc_resp.info[0] if grpc_resp.info else "Failed to create account" }

@app.post("/api/create-post")
def create_post(req: CreatePostRequest):
    stub = find_leader_stub()
    if not stub:
        raise HTTPException(status_code=503, detail="Leader not available")

    grpc_req = blog_pb2.Request(info=[req.title, req.content, req.author])
    grpc_resp = stub.RPCCreatePost(grpc_req)

    if grpc_resp.operation == blog_pb2.SUCCESS:
        return { "success": True }
    return { "success": False, "error": grpc_resp.info[0] if grpc_resp.info else "Failed to create post" }

@app.get("/api/posts")
def get_posts() -> List[Post]:
    stub = find_leader_stub()
    if not stub:
        raise HTTPException(status_code=503, detail="Leader not available")

    grpc_req = blog_pb2.Request()
    grpc_resp = stub.RPCGetPost(grpc_req)

    if grpc_resp.operation == blog_pb2.SUCCESS:
        return [
            Post(
                post_id=post.post_id,
                author=post.author,
                title=post.title,
                content=post.content,
                timestamp=post.timestamp,
                likes=post.likes
            ) for post in grpc_resp.posts
        ]
    return []
