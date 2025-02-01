import React from 'react';
import { Card, Col, Row } from 'antd';
import Navigation from '@/components/Navigation';

export default function News() {
  return (
    <div>
      <div style={{ paddingTop: '2rem', paddingLeft: '2rem' }}>
        <Navigation/>
      </div>
        <div style={{ 
          padding: '20vh 0',
          maxWidth: '1200px',  // Add a max-width to contain the content
          margin: '0 auto',    // Center horizontally with auto margins
          width: '100%'        // Take full width up to maxWidth
        }}>
          <Row gutter={16}>
            <Col span={8}>
              <Card title="Card title" bordered={false}>
                Card content
              </Card>
            </Col>
            <Col span={8}>
              <Card title="Card title" bordered={false}>
                Card content
              </Card>
            </Col>
            <Col span={8}>
              <Card title="Card title" bordered={false}>
                Card content
              </Card>
            </Col>
        </Row>
        </div>
      </div>
  );
}
