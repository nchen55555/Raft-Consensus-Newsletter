import { REPLICA_ENDPOINTS } from '../config/replicas';
import { notification } from 'antd';

class ApiClient {
  private currentLeaderUrl: string | null = null;

  private async findLeader(): Promise<string> {
    // Try each replica until we find the leader
    for (const endpoint of REPLICA_ENDPOINTS) {
      try {
        const response = await fetch(`${endpoint}/leader-info`);
        const data = await response.json();
        
        if (data.isLeader) {
          this.currentLeaderUrl = endpoint;
          return endpoint;
        } else if (data.leaderEndpoint) {
          this.currentLeaderUrl = data.leaderEndpoint;
          return data.leaderEndpoint;
        }
      } catch (error) {
        console.log(`Failed to contact replica at ${endpoint}`);
      }
    }
    throw new Error('No leader found');
  }

  async request(path: string, options: RequestInit = {}): Promise<Response> {
    try {
      // If we don't know the leader, find it
      if (!this.currentLeaderUrl) {
        this.currentLeaderUrl = await this.findLeader();
      }

      // Make sure path starts with /
      const normalizedPath = path.startsWith('/') ? path : `/${path}`;

      // Make the request to the leader
      const response = await fetch(`${this.currentLeaderUrl}${normalizedPath}`, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
      });
      
      // If we get a "not leader" response, clear the leader and retry
      if (response.status === 403) {
        const data = await response.json();
        if (data.error === 'not_leader') {
          this.currentLeaderUrl = null;
          return this.request(path, options);
        }
      }

      return response;
    } catch (error) {
      // If request fails, clear leader and retry once
      if (this.currentLeaderUrl) {
        this.currentLeaderUrl = null;
        return this.request(path, options);
      }
      notification.error({
        message: 'Error',
        description: 'Failed to connect to server',
      });
      throw error;
    }
  }
}

export const apiClient = new ApiClient();
