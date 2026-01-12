/**
 * Markup Configuration Dialog
 *
 * Allows users to configure the desired net profit margin for eBay exports.
 * Accounts for eBay fees and displays final pricing breakdown.
 */
'use client';

import { useState, useEffect, useRef } from 'react';

export interface MarkupDialogProps {
  isOpen: boolean;
  itemCount: number;
  averagePrice: number;
  averageShippingCost: number;
  onConfirm: (markup: number) => void;
  onCancel: () => void;
}

/**
 * eBay fee structure (as of 2024)
 * - Final Value Fee: 13.25% of total sale (item + shipping)
 * - Payment Processing: 2.35% + $0.30 per transaction
 * - International fee: 1.65% for cross-border trade
 */
const EBAY_FINAL_VALUE_FEE = 0.1325; // 13.25%
const EBAY_PAYMENT_PROCESSING_PERCENT = 0.0235; // 2.35%
const EBAY_PAYMENT_PROCESSING_FIXED = 0.30; // $0.30
const EBAY_INTERNATIONAL_FEE = 0.0165; // 1.65%

export function MarkupDialog({
  isOpen,
  itemCount,
  averagePrice,
  averageShippingCost,
  onConfirm,
  onCancel,
}: MarkupDialogProps) {
  const [desiredMargin, setDesiredMargin] = useState<string>('25');
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus input when dialog opens
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isOpen]);

  // Keyboard handling
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onCancel();
      } else if (e.key === 'Enter' && isOpen) {
        handleConfirm();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'hidden';
    }

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, desiredMargin]);

  if (!isOpen) return null;

  const marginPercent = parseFloat(desiredMargin) || 0;
  const avgCostJPY = averagePrice;
  const avgCostUSD = avgCostJPY * 0.0067; // JPY to USD conversion

  /**
   * Calculate required markup to achieve desired net margin after eBay fees
   *
   * Formula:
   * Net Margin = Sale Price - Cost - Shipping - eBay Fees
   * eBay Fees = Sale Price * (FVF + Payment % + Intl %) + Payment Fixed
   *
   * NOTE: Shipping cost (varies by niche) is included in the item price. Buyers see "Free Shipping".
   *
   * Solving for Sale Price given desired margin:
   * Sale Price = (Cost + Shipping + Desired Margin + Payment Fixed) / (1 - Total Fee %)
   */
  const calculatePricing = () => {
    const totalFeePercent =
      EBAY_FINAL_VALUE_FEE + EBAY_PAYMENT_PROCESSING_PERCENT + EBAY_INTERNATIONAL_FEE;

    // Desired net profit
    const desiredProfit = avgCostUSD * (marginPercent / 100);

    // Calculate sale price needed to achieve desired margin
    // Shipping cost is included in the sale price
    const salePrice =
      (avgCostUSD + averageShippingCost + desiredProfit + EBAY_PAYMENT_PROCESSING_FIXED) /
      (1 - totalFeePercent);

    // Calculate actual fees (eBay fees are calculated on sale price only, not shipping)
    const finalValueFee = salePrice * EBAY_FINAL_VALUE_FEE;
    const paymentFee =
      salePrice * EBAY_PAYMENT_PROCESSING_PERCENT + EBAY_PAYMENT_PROCESSING_FIXED;
    const internationalFee = salePrice * EBAY_INTERNATIONAL_FEE;
    const totalFees = finalValueFee + paymentFee + internationalFee;

    // Net profit after all fees (shipping cost already accounted for in sale price)
    const netProfit = salePrice - avgCostUSD - averageShippingCost - totalFees;
    const actualMargin = (netProfit / avgCostUSD) * 100;

    return {
      salePrice: salePrice.toFixed(2),
      finalValueFee: finalValueFee.toFixed(2),
      paymentFee: paymentFee.toFixed(2),
      internationalFee: internationalFee.toFixed(2),
      totalFees: totalFees.toFixed(2),
      netProfit: netProfit.toFixed(2),
      actualMargin: actualMargin.toFixed(1),
      grossMarginPercent: (((salePrice - avgCostUSD) / salePrice) * 100).toFixed(1),
    };
  };

  const pricing = calculatePricing();

  const handleConfirm = () => {
    if (marginPercent < 0 || marginPercent > 500) {
      alert('Please enter a margin between 0% and 500%');
      return;
    }
    onConfirm(marginPercent);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="markup-dialog-title"
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 transition-opacity"
        onClick={onCancel}
        aria-hidden="true"
      />

      {/* Dialog */}
      <div className="relative z-10 w-full max-w-lg transform rounded-lg bg-white p-6 shadow-xl transition-all dark:bg-zinc-900">
        <h3
          id="markup-dialog-title"
          className="text-lg font-semibold text-zinc-900 dark:text-zinc-50"
        >
          Configure eBay Export Pricing
        </h3>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Set your desired net profit margin after eBay fees. Shipping costs (${averageShippingCost.toFixed(2)} avg) are included
          in the item price, so buyers see free shipping.
        </p>

        {/* Margin Input */}
        <div className="mt-6">
          <label
            htmlFor="margin-input"
            className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
          >
            Desired Net Margin (%)
          </label>
          <div className="mt-2 flex items-center gap-2">
            <input
              ref={inputRef}
              id="margin-input"
              type="number"
              min="0"
              max="500"
              step="5"
              value={desiredMargin}
              onChange={(e) => setDesiredMargin(e.target.value)}
              className="block w-32 rounded-lg border border-zinc-300 px-4 py-2 text-zinc-900 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-50"
            />
            <span className="text-sm text-zinc-600 dark:text-zinc-400">%</span>
          </div>
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-500">
            Net profit margin after all eBay fees and shipping costs
          </p>
        </div>

        {/* Pricing Breakdown */}
        <div className="mt-6 rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800/50">
          <h4 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
            Pricing Breakdown (Average per item)
          </h4>
          <div className="mt-3 space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-zinc-600 dark:text-zinc-400">Cost (¥{avgCostJPY.toLocaleString()})</span>
              <span className="font-medium text-zinc-900 dark:text-zinc-50">
                ${avgCostUSD.toFixed(2)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-600 dark:text-zinc-400">Shipping (FedEx International)</span>
              <span className="font-medium text-zinc-900 dark:text-zinc-50">
                ${averageShippingCost.toFixed(2)}
              </span>
            </div>
            <div className="flex justify-between border-t border-zinc-200 pt-2 dark:border-zinc-700">
              <span className="font-medium text-zinc-700 dark:text-zinc-300">Sale Price</span>
              <span className="font-semibold text-blue-600 dark:text-blue-400">
                ${pricing.salePrice}
              </span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-zinc-500 dark:text-zinc-500">
                Gross Margin: {pricing.grossMarginPercent}%
              </span>
            </div>
            <div className="mt-2 flex items-center gap-1 rounded bg-blue-50 px-2 py-1 text-xs text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
              <svg
                className="h-3.5 w-3.5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <span>Shipping included in price • Buyers see "Free Shipping"</span>
            </div>
          </div>

          {/* eBay Fees Breakdown */}
          <div className="mt-4 border-t border-zinc-200 pt-3 dark:border-zinc-700">
            <h5 className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">eBay Fees</h5>
            <div className="mt-2 space-y-1 text-xs">
              <div className="flex justify-between text-zinc-600 dark:text-zinc-400">
                <span>Final Value Fee (13.25%)</span>
                <span>${pricing.finalValueFee}</span>
              </div>
              <div className="flex justify-between text-zinc-600 dark:text-zinc-400">
                <span>Payment Processing (2.35% + $0.30)</span>
                <span>${pricing.paymentFee}</span>
              </div>
              <div className="flex justify-between text-zinc-600 dark:text-zinc-400">
                <span>International Fee (1.65%)</span>
                <span>${pricing.internationalFee}</span>
              </div>
              <div className="flex justify-between border-t border-zinc-200 pt-1 font-medium dark:border-zinc-700">
                <span className="text-zinc-700 dark:text-zinc-300">Total Fees</span>
                <span className="text-red-600 dark:text-red-400">-${pricing.totalFees}</span>
              </div>
            </div>
          </div>

          {/* Net Profit */}
          <div className="mt-4 rounded-lg bg-green-50 p-3 dark:bg-green-900/20">
            <div className="flex justify-between">
              <span className="font-semibold text-green-900 dark:text-green-100">
                Net Profit per Item
              </span>
              <span className="text-lg font-bold text-green-600 dark:text-green-400">
                ${pricing.netProfit}
              </span>
            </div>
            <div className="mt-1 flex justify-between text-xs">
              <span className="text-green-700 dark:text-green-300">Net Margin</span>
              <span className="font-semibold text-green-700 dark:text-green-300">
                {pricing.actualMargin}%
              </span>
            </div>
          </div>

          {/* Total for all items */}
          {itemCount > 1 && (
            <div className="mt-3 text-xs text-zinc-600 dark:text-zinc-400">
              Total net profit for {itemCount} items: $
              {(parseFloat(pricing.netProfit) * itemCount).toFixed(2)}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-semibold text-zinc-700 transition hover:bg-zinc-50 focus:outline-none focus:ring-2 focus:ring-zinc-500 focus:ring-offset-2 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:bg-blue-500 dark:hover:bg-blue-600"
          >
            Export with {desiredMargin}% Margin
          </button>
        </div>
      </div>
    </div>
  );
}
