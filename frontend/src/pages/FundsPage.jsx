/**
 * FundsPage — every staff member can request funds + see their history.
 *
 * Lives at /funds. Distinct from /financial which is finance-only — this page
 * is the "submit a reimbursement / advance" surface for the whole org.
 */
import React from 'react';
import FundRequestsPanel from '../components/FundRequestsPanel';
import { Banknote } from 'lucide-react';

export default function FundsPage() {
  return (
    <div className="p-6 space-y-4 max-w-5xl">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
          <Banknote className="text-primary" size={20} />
        </div>
        <div>
          <h1 className="text-2xl font-semibold font-heading">Fund Requests</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Request advances or claim reimbursements. Track your submissions and upload receipts.
          </p>
        </div>
      </div>
      <FundRequestsPanel />
    </div>
  );
}
