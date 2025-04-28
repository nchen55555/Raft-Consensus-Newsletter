from datetime import datetime
from protos import blog_pb2

class Post:
    def __init__(self, author, title, content, likes=None, post_id=None, timestamp=None):
        self.author = author
        self.title = title
        self.content = content
        self.timestamp = timestamp or datetime.now()
        self.likes = likes if likes is not None else []
        self.post_id = post_id
        self.comments = []
        
    def to_dict(self):
        return {
            "author": self.author,
            "title": self.title,
            "content": self.content,
            "timestamp": str(self.timestamp),
            "likes": self.likes,  # Don't convert to int, it's a list
            "post_id": self.post_id,
            "comments": self.comments
        }
    
    @classmethod
    def from_dict(cls, data):
        post = cls(
            author=data["author"],
            title=data["title"],
            content=data["content"],
            post_id=data["post_id"],
            timestamp=datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
        )
        post.likes = data["likes"]
        post.comments = data["comments"]
        return post

    def to_proto(self):
        """Convert Post object to protobuf Post message"""
        return blog_pb2.Post(
            post_id=self.post_id,
            author=self.author,
            title=self.title,
            content=self.content,
            timestamp=self.timestamp.isoformat(),
            likes=self.likes,
            comments=[c.to_proto() for c in self.comments]  # <-- add this line
        )
    
    @classmethod
    def from_proto(cls, proto_post):
        """Create Post object from protobuf Post message"""
        return cls(
            post_id=proto_post.post_id,
            author=proto_post.author,
            title=proto_post.title,
            content=proto_post.content,
            timestamp=datetime.fromisoformat(proto_post.timestamp),
            likes=proto_post.likes,
            comments=[Comment.from_proto(c) for c in proto_post.comments]  # <-- add this line
        )

    def like(self, username):
        if username not in self.likes:
            self.likes.append(username)
            return True
        return False
        
    def unlike(self, username):
        if username in self.likes:
            self.likes.remove(username)
            return True
        return False