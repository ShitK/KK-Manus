import { createClient } from '@/lib/supabase/server';
import UsageLogs from '@/components/billing/usage-logs';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

export const dynamic = 'force-dynamic';

export default async function UsageLogsPage() {
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
    <div className="space-y-6">
      <UsageLogs accountId={personalAccount.account_id} />
    </div>
  );
}
