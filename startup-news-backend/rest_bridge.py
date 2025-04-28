from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import List, Optional
import grpc
from fastapi.middleware.cors import CORSMiddleware
from protos import blog_pb2, blog_pb2_grpc
from server import find_leader_stub
from email_validator import validate_email, EmailNotValidError
from fastapi import Query

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
    likes: list[str]

class CommentRequest(BaseModel):
    post_id: str
    email: str
    text: str

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
    grpc_resp = stub.RPCGetAllPosts(grpc_req)

    if grpc_resp.operation == blog_pb2.SUCCESS:
        return [
            Post(
                post_id=post.post_id,
                author=post.author,
                title=post.title,
                content=post.content,
                timestamp=post.timestamp,
                likes=post.likes,
                comments=post.comments
            ) for post in grpc_resp.posts
        ]
    return []

@app.get("/api/posts/{post_id}")
def get_post(post_id: str) -> Post:
    stub = find_leader_stub()
    if not stub:
        raise HTTPException(status_code=503, detail="Leader not available")

    grpc_req = blog_pb2.Request(info=[post_id])
    grpc_resp = stub.RPCGetPost(grpc_req)

    if grpc_resp.operation == blog_pb2.SUCCESS and grpc_resp.posts:
        post = grpc_resp.posts[0]
        temp_post = Post(
            post_id=post.post_id,
            author=post.author,
            title=post.title,
            content=post.content,
            timestamp=post.timestamp,
            likes=post.likes,
            comments=post.comments
        )
        return temp_post
    raise HTTPException(status_code=404, detail="Post not found")

@app.get("/api/search_user")
def search_user(email: str = Query(...)):
    stub = find_leader_stub()
    if not stub:
        return {"success": False, "error": "Leader not available"}
    grpc_req = blog_pb2.Request(info=[email])
    grpc_resp = stub.RPCSearchUsers(grpc_req)
    if grpc_resp.operation == blog_pb2.SUCCESS and grpc_resp.info:
        return {"success": True, "email": grpc_resp.info[0]}
    else:
        return {"success": False, "error": "User not found"}

@app.post("/api/comment")
def comment(req: CommentRequest):
    stub = find_leader_stub()
    if not stub:
        return {"success": False, "error": "Leader not available"}

    post_id = req.post_id
    email = req.email
    text = req.text

    grpc_req = blog_pb2.Request(info=[post_id, email, text])
    grpc_resp = stub.RPCCommentPost(grpc_req)
    if grpc_resp.operation == blog_pb2.SUCCESS:
        return {"success": True}
    return {"success": False, "error": "Failed to comment"}

@app.get("/api/comments")
def get_comments(post_id: str = Query(...)) -> dict:
    stub = find_leader_stub()
    if not stub:
        raise HTTPException(status_code=503, detail="Leader not available")
    grpc_req = blog_pb2.Request(info=[post_id])
    grpc_resp = stub.RPCGetPost(grpc_req)
    if grpc_resp.operation == blog_pb2.SUCCESS and grpc_resp.posts:
        post = grpc_resp.posts[0]
        # Assuming post.comments is a list of Comment protos
        comments = [
            {
                "email": c.email,
                "text": c.text,
                "timestamp": c.timestamp
            }
            for c in post.comments
        ]
        return {"comments": comments}
    raise HTTPException(status_code=404, detail="Post not found")

