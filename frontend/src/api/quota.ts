/**
 * Tiny lookup hooks for quota state.
 *
 * Why a separate file: the QuotaCaption + UserQuotaCaption components
 * already do this lookup, but the panels themselves also need to know
 * `atLimit` to disable the generate button. Without these hooks each
 * panel would re-implement the find() against useJob/useBillingStatus.
 *
 * `atLimit` is true only when the plan caps the resource AND remaining
 * is exactly 0 — unlimited (grandfathered) accounts are never atLimit.
 * If the quota row is missing (data not loaded yet, or freshly-created
 * job without a populated quota array), atLimit is false: a missing
 * caption is better than a wrongly-disabled button.
 */
import { useBillingStatus, useJob } from './hooks';
import type { EntitlementResource, QuotaItem } from '@/types/models';

export interface QuotaState {
  item: QuotaItem | null;
  atLimit: boolean;
  isUnlimited: boolean;
}

function fromItem(item: QuotaItem | undefined): QuotaState {
  if (!item) return { item: null, atLimit: false, isUnlimited: false };
  const isUnlimited = item.limit === null || item.remaining === null;
  const atLimit = !isUnlimited && (item.remaining ?? 0) <= 0;
  return { item, atLimit, isUnlimited };
}

export function useJobQuota(
  jobId: string,
  resource: EntitlementResource,
): QuotaState {
  const { data } = useJob(jobId);
  return fromItem(data?.quota.find((q) => q.resource === resource));
}

export function useUserQuota(resource: EntitlementResource): QuotaState {
  const { data } = useBillingStatus();
  return fromItem(data?.usage.find((u) => u.resource === resource));
}
