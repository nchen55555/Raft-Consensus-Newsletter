import { Anchor } from 'antd';

export default function Navigation() {
  return (
      <Anchor
        affix={false}
        items={[
          {
            key: '1',
            href: '/',
            title: 'Welcome',
          },
          {
            key: '2',
            href: '/news',
            title: 'Articles',
          },
          {
            key: '3',
            href: '#about',
            title: 'About',
            children: [
              {
                key: '4',
                href: '#who',
                title: 'Contributors',
              },
              {
                key: '5',
                href: '#apply',
                title: 'Apply to Contribute',
              },
            ],
          },
        ]}
      />
  );
}