'use client';

import React from 'react';
import ReactMarkdown from 'react-markdown';
import Navigation from '@/components/Navigation';
import type { TextAreaRef } from 'antd/es/input/TextArea';
import { useEffect, useState, useRef } from 'react';
import { Input, Button } from 'antd';
import { useRouter } from 'next/navigation';
import { useParams } from 'next/navigation';

export default function PostDetailPage() {
  const params = useParams();
  const post_id = params.post_id;

  const textAreaRef = useRef<TextAreaRef>(null);
  const [commentTexts, setCommentTexts] = useState<{ [postId: string]: string }>({});
  const [commentSubmitting, setCommentSubmitting] = useState<{ [postId: string]: boolean }>({});
  const [comments, setComments] = useState<{ [postId: string]: { email: string; text: string }[] }>({});
  const commentInputRefs = useRef<{ [postId: string]: HTMLTextAreaElement | null }>({});

  const [sessionEmail, setSessionEmail] = useState<string | null>(null);

  const router = useRouter();

  const [post, setPost] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const fetchComments = async (postId: string) => {
    try {
      const response = await fetch(`http://localhost:8000/api/comments?post_id=${encodeURIComponent(postId)}`);
      if (!response.ok) throw new Error('Failed to fetch comments');
      const data = await response.json();
      setComments(prev => ({
        ...prev,
        [postId]: data.comments || [] // Adjust if your backend returns a different shape
      }));
    } catch (error) {
      // Optionally handle error
    }
  };

  useEffect(() => {
    const storedEmail = sessionStorage.getItem('startupnews_email');
    setSessionEmail(storedEmail);
    if (!storedEmail) {
      router.replace('/news');
    }
  }, [router]);

  const handleAddComment = async (postId: string) => {
    if (!sessionEmail || !commentTexts[postId]?.trim()) return;
    setCommentSubmitting(prev => ({ ...prev, [postId]: true }));
    console.log(`Adding comment...${postId}, ${sessionEmail}, ${commentTexts[postId]}`);
    try {
      const response = await fetch('http://localhost:8000/api/comment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          post_id: postId,
          email: sessionEmail,
          text: commentTexts[postId]
        }),
      });

      if (!response.ok) throw new Error('Failed to add comment');

      // Fetch the latest comments from backend here
      await fetchComments(postId);
      setCommentTexts(prev => ({ ...prev, [postId]: '' }));
      // Optionally focus textarea again
      commentInputRefs.current[postId]?.focus();
    } catch (error) {
      // Handle error (show notification, etc.)
    } finally {
      setCommentSubmitting(prev => ({ ...prev, [postId]: false }));
    }
  };

  useEffect(() => {
    // Fetch post data on mount
    const fetchPost = async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/posts/${post_id}`);
        if (!res.ok) throw new Error('Failed to fetch post');
        const data = await res.json();
        setPost(data);
      } catch (err) {
        // handle error
      } finally {
        setLoading(false);
      }
    };
    fetchPost();
  }, [post_id]);

  if (loading) return <div>Loading...</div>;
  if (!post) return <div>Post not found.</div>;

  return (
    <div className="min-h-screen bg-gradient-to-b from-white to-gray-50">
      <div className="px-8 pt-8">
        <Navigation />
      </div>
      <div className="py-20">
        <div className="max-w-7xl mx-auto px-4">
          <h1 className="text-3xl font-bold mb-4 text-black">{post.title}</h1>
          <div className="mb-4 text-gray-700 text-base">
            By {post.author} • {new Date(post.timestamp).toLocaleString()}
          </div>
          <div className="prose prose-lg text-black">
            <ReactMarkdown>{post.content}</ReactMarkdown>
            {/* Comments section */}
            <div className="mt-8 border-t pt-6">
              <h3 className="text-lg font-semibold mb-2">Comments</h3>
              <div className="mb-4">
                {(!post.comments || post.comments.length === 0) ? (
                  <div className="text-gray-400 text-sm">No comments yet.</div>
                ) : (
                  <ul className="space-y-2">
                    {post.comments.map((c: any, idx: number) => (
                      <li key={idx} className="bg-gray-50 rounded px-3 py-2 text-left">
                        <span className="font-medium text-blue-700">{c.email}</span>: {c.text}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="flex items-end gap-2">
                <Input.TextArea
                  ref={textAreaRef}
                  rows={2}
                  value={commentTexts[post.post_id] || ''}
                  onChange={e => setCommentTexts(prev => ({ ...prev, [post.post_id]: e.target.value }))}
                  placeholder={sessionEmail ? 'Add a comment...' : 'Subscribe to comment'}
                  disabled={!sessionEmail || commentSubmitting[post.post_id]}
                  className="flex-1"
                  maxLength={300}
                />
                <Button
                  type="primary"
                  onClick={() => handleAddComment(post.post_id)}
                  disabled={!sessionEmail || !commentTexts[post.post_id]?.trim() || commentSubmitting[post.post_id]}
                  loading={commentSubmitting[post.post_id]}
                >
                  Submit
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
