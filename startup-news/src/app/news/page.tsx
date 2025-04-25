'use client';

import React, { useEffect, useState } from 'react';
import { Card, Col, Row, Space, Spin } from 'antd';
import Navigation from '@/components/Navigation';
import { motion } from 'framer-motion';
import { ClockCircleOutlined, UserOutlined, LikeOutlined } from '@ant-design/icons';

interface Post {
  post_id: string;
  author: string;
  title: string;
  content: string;
  timestamp: string;
  likes: number;
}

export default function News() {
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchPosts = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/posts');
        if (!response.ok) throw new Error('Failed to fetch posts');
        const data = await response.json();
        setPosts(data);
      } catch (error) {
        console.error('Error fetching posts:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchPosts();
  }, []);

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
                        <span>{post.likes}</span>
                      </Space>
                    </Space>
                    <p className="text-gray-600 text-lg">
                      {post.content.length > 200 ? post.content.slice(0, 200) + '...' : post.content}
                    </p>
                    <div className="text-blue-600 hover:text-blue-800">Read more →</div>
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