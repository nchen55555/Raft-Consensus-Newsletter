'use client';

import React, { useState } from 'react';
import { Card, Tabs, Form, Input, Button, notification } from 'antd';
import Navigation from '@/components/Navigation';
import { motion } from 'framer-motion';
import { UserOutlined, LockOutlined, MailOutlined } from '@ant-design/icons';
import dynamic from 'next/dynamic';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { apiClient } from '@/services/apiClient';

const ClientSideLoginForm = dynamic(() => Promise.resolve(({ children }: { children: React.ReactNode }) => <>{children}</>), { ssr: false });

export default function Login() {
  const [activeTab, setActiveTab] = useState('login');
  const [loading, setLoading] = useState(false);
  const [api, contextHolder] = notification.useNotification();
  const router = useRouter();
  const { login } = useAuth();

  const handleLogin = async (values: { email: string; password: string }) => {
    setLoading(true);
    try {
      const response = await apiClient.request('/api/login', {
        method: 'POST',
        body: JSON.stringify(values),
      });
      
      const data = await response.json();
      if (data.success) {
        api.success({
          message: 'Success',
          description: 'Login successful!',
        });
        login(values.email);
        router.push('/post');
      } else {
        api.error({
          message: 'Error',
          description: data.error || 'Login failed',
        });
      }
    } catch (error) {
      api.error({
        message: 'Error',
        description: 'Failed to connect to server',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleCreateAccount = async (values: { email: string; password: string; name: string }) => {
    setLoading(true);
    try {
      const response = await apiClient.request('/api/create-account', {
        method: 'POST',
        body: JSON.stringify(values),
      });
      
      const data = await response.json();
      if (data.success) {
        api.success({
          message: 'Success',
          description: 'Account created successfully!',
        });
        setActiveTab('login'); // Switch to login tab after successful account creation
      } else {
        api.error({
          message: 'Error',
          description: data.error || 'Failed to create account',
        });
      }
    } catch (error) {
      api.error({
        message: 'Error',
        description: 'Failed to connect to server',
      });
    } finally {
      setLoading(false);
    }
  };

  const fadeInUp = {
    initial: { opacity: 0, y: 20 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.6 }
  };

  const items = [
    {
      key: 'login',
      label: 'Login',
      children: (
        <Form layout="vertical" onFinish={handleLogin}>
          <Form.Item
            name="email"
            rules={[
              { required: true, message: 'Please input your email!' },
              { type: 'email', message: 'Please enter a valid email!' }
            ]}
          >
            <Input prefix={<MailOutlined />} placeholder="Email" size="large" className="rounded-lg" />
          </Form.Item>
          <Form.Item
            name="password"
            rules={[
              { required: true, message: 'Please input your password!' },
              { min: 8, message: 'Password must be at least 8 characters!' }
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="Password" size="large" className="rounded-lg" />
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              block
              className={`w-full py-3 px-4 rounded-lg bg-black text-white font-medium text-sm hover:bg-gray-800 transition-colors ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              {loading ? 'Logging in...' : 'Log in'}
            </Button>
          </Form.Item>
        </Form>
      ),
    },
    {
      key: 'create',
      label: 'Create Account',
      children: (
        <Form layout="vertical" onFinish={handleCreateAccount}>
          <Form.Item
            name="name"
            rules={[{ required: true, message: 'Please input your name!' }]}
          >
            <Input prefix={<UserOutlined />} placeholder="Full Name" size="large" className="rounded-lg" />
          </Form.Item>
          <Form.Item
            name="email"
            rules={[
              { required: true, message: 'Please input your email!' },
              { type: 'email', message: 'Please enter a valid email!' }
            ]}
          >
            <Input prefix={<MailOutlined />} placeholder="Email" size="large" className="rounded-lg" />
          </Form.Item>
          <Form.Item
            name="password"
            rules={[
              { required: true, message: 'Please input your password!' },
              { min: 8, message: 'Password must be at least 8 characters!' }
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="Password" size="large" className="rounded-lg" />
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              block
              className={`w-full py-3 px-4 rounded-lg bg-black text-white font-medium text-sm hover:bg-gray-800 transition-colors ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              {loading ? 'Creating account...' : 'Create Account'}
            </Button>
          </Form.Item>
        </Form>
      ),
    },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-b from-white to-gray-50">
      {contextHolder}
      <div className="px-8 pt-8">
        <Navigation/>
      </div>

      {/* Form Section */}
      <div className="py-12">
        <div className="max-w-md mx-auto px-4">
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2 }}
          >
            <ClientSideLoginForm>
              <Card className="shadow-lg border-none bg-white">
                <Tabs
                  activeKey={activeTab}
                  onChange={setActiveTab}
                  items={items}
                  className="auth-tabs"
                />
              </Card>
            </ClientSideLoginForm>
          </motion.div>
        </div>
      </div>
    </div>
  );
}