export const REPLICA_ENDPOINTS = (process.env.NEXT_PUBLIC_REPLICA_ENDPOINTS || '')
  .split(',')
  .filter(Boolean) || [
    'http://localhost:5001/api',  // Default development endpoints
    'http://localhost:5002/api',
    'http://localhost:5003/api',
    'http://localhost:5004/api',
    'http://localhost:5005/api'
  ];
