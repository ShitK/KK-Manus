import EditPersonalAccountName from '@/components/basejump/edit-personal-account-name';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { createClient } from '@/lib/supabase/server';

export const dynamic = 'force-dynamic';

export default async function PersonalAccountSettingsPage() {
  const supabaseClient = await createClient();
  const { data: personalAccount, error } = await supabaseClient.rpc(
    'get_personal_account',
  );

  if (error || !personalAccount) {
    return (
      <Alert
        variant="destructive"
        className="border-red-300 dark:border-red-800 rounded-xl"
      >
        <AlertTitle>Account Not Found</AlertTitle>
        <AlertDescription>
          {error?.message ?? 'Your personal account could not be found.'}
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div>
      <EditPersonalAccountName account={personalAccount} />
    </div>
  );
}
