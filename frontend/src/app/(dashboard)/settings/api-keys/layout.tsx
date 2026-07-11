import { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'API Keys | KKManus',
  description: 'Manage your API keys for programmatic access to KKManus',
  openGraph: {
    title: 'API Keys | KKManus',
    description: 'Manage your API keys for programmatic access to KKManus',
    type: 'website',
  },
};

export default async function APIKeysLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
