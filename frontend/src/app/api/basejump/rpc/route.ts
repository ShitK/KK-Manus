import { NextRequest, NextResponse } from 'next/server';
import { executeBasejumpRpc } from '@/lib/basejump/rpc-server';
import { isBasejumpRpcName } from '@/lib/basejump/rpc-types';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const name = typeof body?.name === 'string' ? body.name : '';

    if (!isBasejumpRpcName(name)) {
      return NextResponse.json(
        { data: null, error: { message: 'Unsupported Basejump RPC' } },
        { status: 400 },
      );
    }

    const args = (body?.args ?? {}) as never;
    const result = await executeBasejumpRpc(name, args);
    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json(
      {
        data: null,
        error: {
          message: error instanceof Error ? error.message : String(error),
        },
      },
      { status: 500 },
    );
  }
}
