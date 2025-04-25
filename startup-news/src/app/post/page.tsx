'use client';

import React, { useEffect } from 'react';
import { Card, Form, Input, Button, notification } from 'antd';
import Navigation from '@/components/Navigation';
import { motion } from 'framer-motion';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';

const { TextArea } = Input;

export default function PostPage() {
  const { isAuthenticated, userEmail } = useAuth();
  const router = useRouter();
  const [form] = Form.useForm();
  const [api, contextHolder] = notification.useNotification();

  useEffect(() => {
    // Redirect to login if not authenticated
    if (!isAuthenticated) {
      router.push('/login');
    }
  }, [isAuthenticated, router]);

  const handleSubmit = async (values: { title: string; content: string }) => {
    try {
      const response = await fetch('http://localhost:8000/api/create-post', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...values,
          author: userEmail,
        }),
      });

      const data = await response.json();
      if (data.success) {
        api.success({
          message: 'Success',
          description: 'Post created successfully!',
        });
        form.resetFields();
        router.push('/news'); // Redirect to news feed after posting
      } else {
        api.error({
          message: 'Error',
          description: data.error || 'Failed to create post',
        });
      }
    } catch (error) {
      api.error({
        message: 'Error',
        description: 'Failed to connect to server',
      });
    }
  };

  if (!isAuthenticated) {
    return null; // Don't render anything while redirecting
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-white to-gray-50">
      {contextHolder}
      <div className="px-8 pt-8">
        <Navigation/>
      </div>

      <div className="py-12">
        <div className="max-w-4xl mx-auto px-4">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8 }}
          >
            <Card className="shadow-lg border-none bg-white">
              <h1 className="text-2xl font-bold mb-6">Create a Post</h1>
              <Form
                form={form}
                layout="vertical"
                onFinish={handleSubmit}
                className="space-y-4"
              >
                <Form.Item
                  name="title"
                  label="Title"
                  rules={[
                    { required: true, message: 'Please enter a title!' },
                    { max: 100, message: 'Title must be less than 100 characters!' }
                  ]}
                >
                  <Input 
                    size="large"
                    placeholder="Enter your post title"
                    className="rounded-lg"
                  />
                </Form.Item>

                <Form.Item
                  name="content"
                  label="Content"
                  rules={[
                    { required: true, message: 'Please enter your post content!' },
                    { max: 5000, message: 'Content must be less than 5000 characters!' }
                  ]}
                >
                  <TextArea
                    rows={6}
                    placeholder="Write your post content here..."
                    className="rounded-lg"
                  />
                </Form.Item>

                <Form.Item>
                  <Button
                    type="primary"
                    htmlType="submit"
                    className="w-full py-3 px-4 rounded-lg bg-black text-white font-medium text-sm hover:bg-gray-800 transition-colors"
                  >
                    Publish Post
                  </Button>
                </Form.Item>
              </Form>
            </Card>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
