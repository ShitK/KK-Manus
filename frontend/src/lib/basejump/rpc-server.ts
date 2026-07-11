import 'server-only';

import { Pool } from 'pg';
import type { PoolClient } from 'pg';
import type {
  BasejumpRpcArgs,
  BasejumpRpcName,
  BasejumpRpcResponse,
  BasejumpRpcResult,
} from './rpc-types';

const pool = new Pool({
  host: process.env.DB_HOST || 'localhost',
  port: parseInt(process.env.DB_PORT || '5432', 10),
  database: process.env.DB_NAME || 'kortix',
  user: process.env.DB_USER || 'postgres',
  password: process.env.DB_PASSWORD || 'password',
  max: 20,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 2000,
});

type QueryMode = 'single' | 'many' | 'boolean';
const allowMissingFunctionFallback =
  process.env.NODE_ENV !== 'production' ||
  process.env.KKMANUS_ALLOW_BASEJUMP_RPC_FALLBACK === 'true';

function isMissingPostgresFunction(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    (error as { code?: string }).code === '42883'
  );
}

async function runRpcQuery<T>(
  sql: string,
  params: unknown[] = [],
  mode: QueryMode = 'single',
  missingFunctionFallback?: T,
): Promise<BasejumpRpcResponse<T>> {
  let client: PoolClient | null = null;

  try {
    client = await pool.connect();
    const result = await client.query(sql, params);

    if (mode === 'many') {
      return { data: result.rows as T, error: null };
    }

    if (mode === 'boolean') {
      return { data: true as T, error: null };
    }

    return { data: result.rows[0] as T, error: null };
  } catch (error) {
    if (
      missingFunctionFallback !== undefined &&
      allowMissingFunctionFallback &&
      isMissingPostgresFunction(error)
    ) {
      console.warn(`[Basejump RPC] Missing local function; returning fallback for: ${sql}`);
      return { data: missingFunctionFallback, error: null };
    }

    return {
      data: null,
      error: {
        message: error instanceof Error ? error.message : String(error),
      },
    };
  } finally {
    client?.release();
  }
}

function asPrimaryOwnerBoolean(value: FormDataEntryValue | null): boolean {
  return value === 'true' || value === 'on' || value === '1';
}

export async function executeBasejumpRpc<TName extends BasejumpRpcName>(
  name: TName,
  args = {} as BasejumpRpcArgs<TName>,
): Promise<BasejumpRpcResponse<BasejumpRpcResult<TName>>> {
  switch (name) {
    case 'get_personal_account':
      return runRpcQuery<BasejumpRpcResult<TName>>('SELECT * FROM get_personal_account()');
    case 'get_accounts':
      return runRpcQuery<BasejumpRpcResult<TName>>(
        'SELECT * FROM get_accounts()',
        [],
        'many',
        [] as BasejumpRpcResult<TName>,
      );
    case 'get_account_by_slug':
      return runRpcQuery<BasejumpRpcResult<TName>>('SELECT * FROM get_account_by_slug($1)', [
        (args as BasejumpRpcArgs<'get_account_by_slug'>).slug,
      ]);
    case 'get_account_members':
      return runRpcQuery<BasejumpRpcResult<TName>>('SELECT * FROM get_account_members($1)', [
        (args as BasejumpRpcArgs<'get_account_members'>).account_id,
      ], 'many');
    case 'get_account_invitations':
      return runRpcQuery<BasejumpRpcResult<TName>>('SELECT * FROM get_account_invitations($1)', [
        (args as BasejumpRpcArgs<'get_account_invitations'>).account_id,
      ], 'many');
    case 'lookup_invitation':
      return runRpcQuery<BasejumpRpcResult<TName>>('SELECT * FROM lookup_invitation($1)', [
        (args as BasejumpRpcArgs<'lookup_invitation'>).lookup_invitation_token,
      ]);
    case 'create_account':
      return runRpcQuery<BasejumpRpcResult<TName>>('SELECT * FROM create_account($1, $2)', [
        (args as BasejumpRpcArgs<'create_account'>).name,
        (args as BasejumpRpcArgs<'create_account'>).slug,
      ]);
    case 'update_account':
      return runRpcQuery<BasejumpRpcResult<TName>>('SELECT * FROM update_account($1, $2, $3)', [
        (args as BasejumpRpcArgs<'update_account'>).account_id,
        (args as BasejumpRpcArgs<'update_account'>).name ?? null,
        (args as BasejumpRpcArgs<'update_account'>).slug ?? null,
      ]);
    case 'create_invitation':
      return runRpcQuery<BasejumpRpcResult<TName>>('SELECT * FROM create_invitation($1, $2, $3)', [
        (args as BasejumpRpcArgs<'create_invitation'>).account_id,
        (args as BasejumpRpcArgs<'create_invitation'>).invitation_type,
        (args as BasejumpRpcArgs<'create_invitation'>).account_role,
      ]);
    case 'delete_invitation':
      return runRpcQuery<BasejumpRpcResult<TName>>('SELECT delete_invitation($1)', [
        (args as BasejumpRpcArgs<'delete_invitation'>).invitation_id,
      ], 'boolean');
    case 'accept_invitation':
      return runRpcQuery<BasejumpRpcResult<TName>>('SELECT * FROM accept_invitation($1)', [
        (args as BasejumpRpcArgs<'accept_invitation'>).lookup_invitation_token,
      ]);
    case 'remove_account_member':
      return runRpcQuery<BasejumpRpcResult<TName>>('SELECT remove_account_member($1, $2)', [
        (args as BasejumpRpcArgs<'remove_account_member'>).user_id,
        (args as BasejumpRpcArgs<'remove_account_member'>).account_id,
      ], 'boolean');
    case 'update_account_user_role':
      return runRpcQuery<BasejumpRpcResult<TName>>(
        'SELECT update_account_user_role($1, $2, $3, $4)',
        [
          (args as BasejumpRpcArgs<'update_account_user_role'>).user_id,
          (args as BasejumpRpcArgs<'update_account_user_role'>).account_id,
          (args as BasejumpRpcArgs<'update_account_user_role'>).new_account_role,
          asPrimaryOwnerBoolean(
            (args as BasejumpRpcArgs<'update_account_user_role'>).make_primary_owner,
          ),
        ],
        'boolean',
      );
  }
}
