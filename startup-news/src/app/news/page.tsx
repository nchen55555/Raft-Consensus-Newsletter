'use client';

import React, { useEffect, useState, useRef } from 'react';
import { Card, Col, Row, Space, Spin, Input, Button, notification } from 'antd';
import Navigation from '@/components/Navigation';
import { motion } from 'framer-motion';
import { ClockCircleOutlined, UserOutlined, LikeOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import Link from 'next/link';
import Subscribe from '@/components/Subscribe';
import { apiClient } from '@/services/apiClient';

interface Comment {
  text: string;
  email: string;
  timestamp: string;
  post_id: string;
}

interface Post {
  post_id: string;
  author: string;
  title: string;
  content: string;
  timestamp: string;
  likes: string[];
  comments: Comment[];
}

// Helper to show only first 2 lines of markdown (approximate)
function getMarkdownPreview(content: string, lines: number = 2): string {
  if (!content) return '';
  // Split by line breaks, take first N non-empty lines
  const allLines = content.split(/\r?\n/).filter(line => line.trim() !== '');
  return allLines.slice(0, lines).join('\n') + (allLines.length > lines ? '\n...' : '');
}

export default function News() {
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [sessionEmail, setSessionEmail] = useState<string | null>(null);

  const [showVerify, setShowVerify] = React.useState(false);
  const [verifyEmail, setVerifyEmail] = React.useState('');
  const [verifying, setVerifying] = React.useState(false);
  const [verifyError, setVerifyError] = React.useState('');

  // Initialize session email from storage
  useEffect(() => {
    const storedEmail = sessionStorage.getItem('startupnews_email');
    setSessionEmail(storedEmail);
  }, []); // Only run once on mount

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const response = await apiClient.request('/posts');
        if (!response.ok) throw new Error('Failed to fetch posts');
        const data = await response.json();
        setPosts(data || []); 
      } catch (error) {
        console.error('Error fetching posts:', error);
      } finally {
        setLoading(false);
      }
    };

    // Only fetch if we have a session email
    if (sessionEmail) {
      fetchData();
    }
  }, [sessionEmail]); // Re-run when sessionEmail changes

  useEffect(() => {
    console.log(`posts present ${posts.length}`);
  }, [posts]);

  useEffect(() => {
    const onStorage = () => {
      const storedEmail = sessionStorage.getItem('startupnews_email');
      setSessionEmail(storedEmail);
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  if (!sessionEmail) {
    const handleVerify = async () => {
      setVerifying(true);
      setVerifyError('');
      try {
        const resp = await apiClient.request(`/search_user?email=${encodeURIComponent(verifyEmail)}`);
        const result = await resp.json();
        if (result.success) {
          sessionStorage.setItem('startupnews_email', verifyEmail);
          window.location.reload();
        } else {
          setVerifyError('Email not found. Please subscribe or check your email.');
        }
      } catch (err) {
        setVerifyError('Verification failed. Please try again.');
      }
      setVerifying(false);
    };

    return (
      <div className="min-h-screen bg-gradient-to-b from-white to-gray-50 flex flex-col">
        <div className="px-8 pt-8">
          <Navigation/>
        </div>
        <div className="flex flex-1 items-center justify-center">
          <motion.div
            className="w-full max-w-xl mx-auto px-6 py-12 text-center bg-white rounded-2xl shadow-2xl flex flex-col items-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8 }}
          >
            <h2 className="text-4xl font-bold mb-4 text-black">Stay in the Loop</h2>
            <p className="text-gray-600 mb-8 text-lg">
              One curated startup deep-dive every week.<br />No fluff, just insights.
            </p>
            <div className="w-full">
              {showVerify ? (
                <div className="flex flex-col items-center gap-4">
                  <input
                    type="email"
                    className="border border-gray-300 rounded-lg px-4 py-2 w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="Enter your email to verify"
                    value={verifyEmail}
                    onChange={e => setVerifyEmail(e.target.value)}
                    disabled={verifying}
                  />
                  <button
                    className="w-full bg-blue-600 text-white py-2 rounded-lg font-medium hover:bg-blue-700 transition-colors disabled:opacity-50"
                    onClick={handleVerify}
                    disabled={verifying}
                  >
                    {verifying ? 'Verifying...' : 'Verify'}
                  </button>
                  {verifyError && <div className="text-red-500 text-sm">{verifyError}</div>}
                  <button className="text-blue-600 mt-2" onClick={() => setShowVerify(false)}>
                    Back to Subscribe
                  </button>
                </div>
              ) : (
                <>
                  <Subscribe onSubscribed={(email) => setSessionEmail(email)} />
                  <div className="mt-6">
                    <button
                      className="text-blue-600 underline hover:text-blue-800 text-base"
                      onClick={() => setShowVerify(true)}
                    >
                      Already subscribed? Click here to access
                    </button>
                  </div>
                </>
              )}
            </div>
          </motion.div>
        </div>
      </div>
    );
  }

  const fadeInUp = {
    initial: { opacity: 0, y: 20 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.6 }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-white to-gray-50">
      <div className="px-8 pt-8">
        <Navigation/>
      </div>
      {/* Hero Section */}
      <motion.div 
        className="flex flex-col items-center justify-center py-16 px-4 max-w-6xl mx-auto text-center"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.8 }}
      >
        <motion.div {...fadeInUp}>
          <h1 className="text-4xl font-bold mb-6 bg-gradient-to-r from-black to-gray-600 bg-clip-text text-transparent">
            Latest Articles
          </h1>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto leading-relaxed mb-8">
            Deep dives into startup engineering, product, and growth
          </p>
        </motion.div>
      </motion.div>

      {/* Articles Section */}
      <div className="py-12 bg-white">
        <div className="max-w-6xl mx-auto px-4">
          {loading ? (
            <div className="flex justify-center py-12">
              <Spin size="large" />
            </div>
          ) : (
            <motion.div 
              className="grid gap-8"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.2 }}
            >
              {posts.map((post) => (
                <Card 
                  key={post.post_id}
                  className="hover:shadow-lg transition-all duration-300 cursor-pointer"
                  styles={{ body: { padding: '2rem' } }}
                >
                  <Space direction="vertical" size="middle">
                    <h2 className="text-2xl font-semibold">{post.title}</h2>
                    <Space className="text-gray-500">
                      <Space>
                        <UserOutlined />
                        <span>{post.author}</span>
                      </Space>
                      <Space>
                        <ClockCircleOutlined />
                        <span>{new Date(post.timestamp).toLocaleDateString()}</span>
                      </Space>
                      <Space>
                        <LikeOutlined />
                        <span>{post.likes.length}</span>
                      </Space>
                    </Space>
                    <ReactMarkdown>{getMarkdownPreview(post.content)}</ReactMarkdown>
                    <Link href={`/news/${post.post_id}`} legacyBehavior>
                      <a className="text-blue-600 hover:text-blue-800">Read more →</a>
                    </Link>
                  </Space>
                </Card>
              ))}
            </motion.div>
          )}
        </div>
      </div>
    </div>
    
  );
}