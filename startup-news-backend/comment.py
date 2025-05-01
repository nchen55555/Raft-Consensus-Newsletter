from datetime import datetime
from protos import blog_pb2

class Comment: 
    def __init__(self, post_id, email, text, timestamp):
        self.post_id = post_id
        self.email = email
        self.text = text
        self.timestamp = timestamp

    def to_dict(self):
        return {
            "post_id": self.post_id,
            "email": self.email,
            "text": self.text,
            "timestamp": str(self.timestamp)
        }
        
    @classmethod
    def from_dict(cls, data):
        return cls(
            post_id=data["post_id"],
            email=data["email"],
            text=data["text"],
            timestamp=datetime.fromisoformat(data["timestamp"]) if data["timestamp"] else None
        )
    
    @classmethod
    def from_proto(cls, proto_comment):
        return cls(
            post_id=proto_comment.post_id,
            email=proto_comment.email,
            text=proto_comment.text,
            timestamp=datetime.fromisoformat(proto_comment.timestamp)
        )
        
    def to_proto(self):
        return blog_pb2.Comment(
            post_id=self.post_id,
            email=self.email,
            text=self.text,
            timestamp=self.timestamp.isoformat()
        )