import AcceptTeamInvitation from '@/components/basejump/accept-team-invitation';
import { redirect } from 'next/navigation';

type InvitationSearchParams = {
  token?: string;
};

export default async function AcceptInvitationPage({
  searchParams,
}: {
  searchParams: Promise<InvitationSearchParams>;
}) {
  const unwrappedSearchParams = await searchParams;

  if (!unwrappedSearchParams.token) {
    redirect('/');
  }

  return (
    <div className="max-w-md mx-auto w-full my-12">
      <AcceptTeamInvitation token={unwrappedSearchParams.token} />
    </div>
  );
}
