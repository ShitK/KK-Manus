import type {
  AcceptInvitationResponse,
  CreateAccountResponse,
  CreateInvitationResponse,
  GetAccountInvitesResponse,
  GetAccountMembersResponse,
  GetAccountResponse,
  GetAccountsResponse,
  LookupInvitationResponse,
  UpdateAccountResponse,
} from '@usebasejump/shared';

export type BasejumpRpcResponse<T> = {
  data: T | null;
  error: { message: string } | null;
};

export type BasejumpRpcMap = {
  get_personal_account: { args: Record<string, never>; result: GetAccountResponse };
  get_accounts: { args: Record<string, never>; result: GetAccountsResponse };
  get_account_by_slug: { args: { slug: string }; result: GetAccountResponse };
  get_account_members: { args: { account_id: string }; result: GetAccountMembersResponse };
  get_account_invitations: { args: { account_id: string }; result: GetAccountInvitesResponse };
  lookup_invitation: { args: { lookup_invitation_token: string }; result: LookupInvitationResponse };
  create_account: { args: { name: string; slug: string }; result: CreateAccountResponse };
  update_account: { args: { account_id: string; name?: string; slug?: string }; result: UpdateAccountResponse };
  create_invitation: {
    args: { account_id: string; invitation_type: string; account_role: string };
    result: CreateInvitationResponse;
  };
  delete_invitation: { args: { invitation_id: string }; result: boolean };
  accept_invitation: { args: { lookup_invitation_token: string }; result: AcceptInvitationResponse };
  remove_account_member: { args: { user_id: string; account_id: string }; result: boolean };
  update_account_user_role: {
    args: {
      user_id: string;
      account_id: string;
      new_account_role: string;
      make_primary_owner: FormDataEntryValue | null;
    };
    result: boolean;
  };
};

export type BasejumpRpcName = keyof BasejumpRpcMap;
export type BasejumpRpcArgs<TName extends BasejumpRpcName> = BasejumpRpcMap[TName]['args'];
export type BasejumpRpcResult<TName extends BasejumpRpcName> = BasejumpRpcMap[TName]['result'];

export const BASEJUMP_RPC_NAMES = [
  'get_personal_account',
  'get_accounts',
  'get_account_by_slug',
  'get_account_members',
  'get_account_invitations',
  'lookup_invitation',
  'create_account',
  'update_account',
  'create_invitation',
  'delete_invitation',
  'accept_invitation',
  'remove_account_member',
  'update_account_user_role',
] as const satisfies readonly BasejumpRpcName[];

export function isBasejumpRpcName(name: string): name is BasejumpRpcName {
  return (BASEJUMP_RPC_NAMES as readonly string[]).includes(name);
}
