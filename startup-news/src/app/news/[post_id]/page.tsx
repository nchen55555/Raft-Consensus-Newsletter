'use client';

import { apiClient } from '@/services/apiClient';
import { useState, useEffect, useRef } from 'react';
import { Card, Input, Button, notification } from 'antd';
import type { TextAreaRef } from 'antd/es/input/TextArea';
import { Comment, Post } from '@/types';
import ReactMarkdown from 'react-markdown';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import { useParams } from 'next/navigation';
import { HeartOutlined, HeartFilled } from '@ant-design/icons';
import { motion } from 'framer-motion';

export default function PostDetailPage() {
  const params = useParams();
  const post_id = params.post_id as string;
  const { userEmail: sessionEmail } = useAuth();
  const router = useRouter();
  const [post, setPost] = useState<Post | null>(null);
  const [loading, setLoading] = useState(false);
  const [likeSubmitting, setLikeSubmitting] = useState(false);
  const [commentSubmitting, setCommentSubmitting] = useState<Record<string, boolean>>({});
  const [commentTexts, setCommentTexts] = useState<Record<string, string>>({});
  const commentInputRefs = useRef<Record<string, TextAreaRef>>({});
  const [api, contextHolder] = notification.useNotification();

  const fetchComments = async (postId: string) => {
    try {
      console.log(`Fetched Comments!`);
      const response = await apiClient.request(`/comments?post_id=${encodeURIComponent(postId)}`);
      if (!response.ok) throw new Error('Failed to fetch comments');
      const data = await response.json();
      setCommentTexts(prev => ({ ...prev, [postId]: '' }));
      if (post) {
        setPost({
          ...post,
          comments: data.comments || []
        });
      }
    } catch (error) {
      console.error('Failed to fetch comments:', error);
    }
  };

  useEffect(() => {
    if (!sessionEmail) {
      router.push('/login');
    }
  }, [router, sessionEmail]);

  useEffect(() => {
    if (post_id) {
      fetchComments(post_id);
    }
  }, [post_id]);

  const handleAddComment = async (values: { text: string }) => {
    if (!sessionEmail || !values.text.trim()) return;
    
    setCommentSubmitting(prev => ({
      ...prev,
      [post_id]: true
    }));
    
    try {
      const response = await apiClient.request('/comment', {
        method: 'POST',
        body: JSON.stringify({
          post_id: post_id,
          email: sessionEmail,
          text: values.text,
          timestamp: new Date().toISOString()
        }),
      });

      if (!response.ok) throw new Error('Failed to add comment');

      // Refresh the entire post to get updated comments
      const postRes = await apiClient.request(`/posts/${post_id}`);
      if (!postRes.ok) throw new Error('Failed to fetch updated post');
      const updatedPost = await postRes.json();
      setPost(updatedPost);
      
      // Clear comment text and focus input
      setCommentTexts(prev => ({
        ...prev,
        [post_id]: ''
      }));
      
      // Optionally focus textarea again
      const inputRef = commentInputRefs.current[post_id];
      if (inputRef) {
        inputRef.focus();
      }
    } catch (error) {
      api.error({
        message: 'Error',
        description: 'Failed to add comment',
      });
    } finally {
      setCommentSubmitting(prev => ({
        ...prev,
        [post_id]: false
      }));
    }
  };

  const handleLike = async () => {
    if (!sessionEmail || !post) return;
    setLikeSubmitting(true);
    try {
      const response = await apiClient.request('/like', {
        method: 'POST',
        body: JSON.stringify({
          post_id: post.post_id,
          email: sessionEmail
        }),
      });

      if (!response.ok) throw new Error('Failed to like post');

      // Refresh post data to get updated likes
      const postRes = await apiClient.request(`/posts/${post.post_id}`);
      if (!postRes.ok) throw new Error('Failed to fetch updated post');
      const updatedPost = await postRes.json();
      setPost(updatedPost);
    } catch (error) {
      api.error({
        message: 'Error',
        description: 'Failed to like post',
      });
    } finally {
      setLikeSubmitting(false);
    }
  };

  useEffect(() => {
    // Fetch post data on mount
    const fetchPost = async () => {
      try {
        const res = await apiClient.request(`/posts/${post_id}`);
        if (!res.ok) throw new Error('Failed to fetch post');
        const data = await res.json();
        setPost(data);
      } catch (error) {
        console.error('Failed to fetch post:', error);
      }
    };

    if (post_id) {
      fetchPost();
    }
  }, [post_id]);

  if (!post) return <div>Loading...</div>;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="container mx-auto px-4 py-8"
    >
      {contextHolder}
      <Card className="w-full max-w-4xl mx-auto">
        <div className="mb-8">
          <h1 className="text-2xl font-bold mb-4">{post.title}</h1>
          <div className="prose max-w-none">
            <ReactMarkdown>{post.content}</ReactMarkdown>
          </div>
          <div className="mt-4 flex items-center justify-between text-gray-500">
            <span>By {post.author}</span>
            <div className="flex items-center gap-2">
              <Button
                type="text"
                icon={post.likes.includes(sessionEmail || '') ? <HeartFilled /> : <HeartOutlined />}
                onClick={handleLike}
                loading={likeSubmitting}
              >
                {post.likes.length} likes
              </Button>
            </div>
          </div>
        </div>

        <div className="mt-8">
          <h2 className="text-xl font-semibold mb-4">Comments</h2>
          {post.comments.map((comment, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3, delay: index * 0.1 }}
              className="mb-4 p-4 bg-gray-50 rounded-lg"
            >
              <div className="flex justify-between items-start">
                <div>
                  <p className="font-medium">{comment.email}</p>
                  <p className="mt-1">{comment.text}</p>
                </div>
                <span className="text-sm text-gray-500">
                  {new Date(comment.timestamp).toLocaleDateString()}
                </span>
              </div>
            </motion.div>
          ))}

          <div className="mt-6">
            <div className="mb-2">
              {!sessionEmail && (
                <p className="text-sm text-gray-500 mb-2">
                  Please login to comment
                </p>
              )}
            </div>
            <div className="flex items-end gap-2">
              <Input.TextArea
                ref={(ref) => {
                  if (ref) {
                    commentInputRefs.current[post_id] = ref;
                  }
                }}
                rows={2}
                value={commentTexts[post_id] || ''}
                onChange={e => setCommentTexts(prev => ({ ...prev, [post_id]: e.target.value }))}
                placeholder={sessionEmail ? 'Add a comment...' : 'Subscribe to comment'}
                disabled={!sessionEmail || commentSubmitting[post_id]}
                className="flex-1"
                maxLength={300}
              />
              <Button
                type="primary"
                onClick={() => handleAddComment({ text: commentTexts[post_id] || '' })}
                disabled={!sessionEmail || !commentTexts[post_id]?.trim() || commentSubmitting[post_id]}
                loading={commentSubmitting[post_id]}
              >
                Submit
              </Button>
            </div>
          </div>
        </div>
      </Card>
    </motion.div>
  );
}
