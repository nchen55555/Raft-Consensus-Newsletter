export interface Comment {
  email: string;
  text: string;
  timestamp: string;
}

export interface Post {
  post_id: string;
  title: string;
  content: string;
  author: string;
  likes: string[];
  comments: Comment[];
  timestamp: string;
}
