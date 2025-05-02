from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import List, Optional
import grpc
from protos import blog_pb2, blog_pb2_grpc
from server import find_leader_stub, get_server_instance
from email_validator import validate_email, EmailNotValidError
from fastapi import Query

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Local development
        "http://10.250.89.39:3000",  # Local network access
        "http://10.250.243.174:3000" # Local network access
    ],
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
    comments: list[dict]

class CommentRequest(BaseModel):
    post_id: str
    email: str
    text: str
    timestamp: str

class LikeRequest(BaseModel):
    post_id: str
    email: str

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
    print("Inside create-post endpoint...")
    stub = find_leader_stub()
    if not stub:
        raise HTTPException(status_code=503, detail="Leader not available")
    print("Stub found")
    grpc_req = blog_pb2.Request(info=[req.title, req.content, req.author])
    print("Request created")
    grpc_resp = stub.RPCCreatePost(grpc_req)
    print("Response received")

    if grpc_resp.operation == blog_pb2.SUCCESS:
        return { "success": True }
    return { "success": False, "error": grpc_resp.info[0] if grpc_resp.info else "Failed to create post" }

@app.get("/api/posts")
def get_posts() -> List[Post]:
    try:
        print("1. INSIDE GETTING POSTS")
        stub = find_leader_stub()
        print("2. Got stub:", stub)
        if not stub:
            raise HTTPException(status_code=503, detail="Leader not available")
        print("3. Stub found")
        grpc_req = blog_pb2.Request()
        print("4. Request created:", grpc_req)
        grpc_resp = stub.RPCGetAllPosts(grpc_req)
        print("5. Got response from leader:", grpc_resp)

        if grpc_resp.operation == blog_pb2.SUCCESS:
            print("6. Response success, posts:", grpc_resp.posts)
            return [
                Post(
                    post_id=post.post_id,
                    author=post.author,
                    title=post.title,
                    content=post.content,
                    timestamp=post.timestamp,
                    likes=list(post.likes),
                    comments=[{
                        'post_id': comment.post_id,
                        'email': comment.email,
                        'text': comment.text,
                        'timestamp': comment.timestamp
                    } for comment in post.comments]
                ) for post in grpc_resp.posts
            ]
        print("7. Response failure")
        return []
    except Exception as e:
        print("8. Error in get_posts:", str(e))
        raise

@app.get("/api/posts/{post_id}")
def get_post(post_id: str) -> Post:
    stub = find_leader_stub()
    if not stub:
        raise HTTPException(status_code=503, detail="Leader not available")

    grpc_req = blog_pb2.Request(info=[post_id])
    grpc_resp = stub.RPCGetPost(grpc_req)

    if grpc_resp.operation == blog_pb2.SUCCESS and grpc_resp.posts:
        post = grpc_resp.posts[0]
        comments = []
        for comment in post.comments:
            comments.append({
                'post_id': comment.post_id,
                'email': comment.email,
                'text': comment.text,
                'timestamp': comment.timestamp
            })
        temp_post = Post(
            post_id=post.post_id,
            author=post.author,
            title=post.title,
            content=post.content,
            timestamp=post.timestamp,
            likes=list(post.likes),  # Convert to list
            comments=comments
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
    try:
        print("Finding leader stub...")
        stub = find_leader_stub()
        if not stub:
            print("No leader available")
            return {"success": False, "error": "Leader not available"}

        post_id = req.post_id
        email = req.email
        text = req.text
        timestamp = req.timestamp
        print(f"Making gRPC request with post_id={post_id}, email={email}, text={text}, timestamp={timestamp}")

        grpc_req = blog_pb2.Request(info=[post_id, email, text, timestamp])
        grpc_resp = stub.RPCCommentPost(grpc_req)

        if grpc_resp.operation == blog_pb2.SUCCESS:
            return {"success": True}
        return {"success": False, "error": grpc_resp.info[0] if grpc_resp.info else "Failed to comment"}
    except Exception as e:
        import traceback
        print("Exception in comment endpoint:")
        print(str(e))
        print("Traceback:")
        print(traceback.format_exc())
        return {"success": False, "error": f"Server error: {str(e)}"}

@app.get("/api/comments")
def get_comments(post_id: str = Query(...)) -> dict:
    stub = find_leader_stub()
    if not stub:
        raise HTTPException(status_code=503, detail="Leader not available")

    print("Inside the fetching comments...")
    grpc_req = blog_pb2.Request(info=[post_id])
    print("Acquired the request...")
    grpc_resp = stub.RPCGetComments(grpc_req)
    print("Got the response...")
    if grpc_resp.operation == blog_pb2.SUCCESS:
        comments = [
            {
                "email": c.email,
                "text": c.text,
                "timestamp": c.timestamp
            }
            for c in grpc_resp.comments
        ]
        print("GRPC has found comments: ", comments)
        return {"comments": comments}
    raise HTTPException(status_code=404, detail="Post not found")

@app.post("/api/like")
def like_post(req: LikeRequest):
    try:
        print("Finding leader stub...")
        stub = find_leader_stub()
        if not stub:
            print("No leader available")
            return {"success": False, "error": "Leader not available"}

        post_id = req.post_id
        email = req.email
        print(f"Making gRPC request with post_id={post_id}, email={email}")

        grpc_req = blog_pb2.Request(info=[post_id, email])
        grpc_resp = stub.RPCLikePost(grpc_req)

        if grpc_resp.operation == blog_pb2.SUCCESS:
            return {"success": True}
        return {"success": False, "error": grpc_resp.info[0] if grpc_resp.info else "Failed to like post"}
    except Exception as e:
        import traceback
        print("Exception in like endpoint:")
        print(str(e))
        print("Traceback:")
        print(traceback.format_exc())
        return {"success": False, "error": f"Server error: {str(e)}"}

@app.get("/api/leader-info")
async def leader_info():
    try:
        stub = find_leader_stub()
        if stub:
            return {"isLeader": True}  # If we found the leader, this endpoint is the leader
        return {"isLeader": False}  # If we couldn't find a leader
    except Exception as e:
        print(f"Error in leader_info: {e}")
        return {"isLeader": False}
