/**
 * Export Modal Component
 *
 * Multi-step export modal supporting eBay and Shopify platforms.
 * Step 1: Select platform
 * Step 2: Configure pricing (margin for eBay, price markup for Shopify)
 */
'use client';

import { useState, useEffect, useRef } from 'react';

export type ExportPlatform = 'ebay' | 'shopify';

export interface ExportModalProps {
  isOpen: boolean;
  itemCount: number;
  averagePrice: number;
  averageShippingCost: number;
  onConfirm: (platform: ExportPlatform, margin: number) => void;
  onCancel: () => void;
}

/**
 * eBay fee structure
 */
const EBAY_FINAL_VALUE_FEE = 0.1325;
const EBAY_PAYMENT_PROCESSING_PERCENT = 0.0235;
const EBAY_PAYMENT_PROCESSING_FIXED = 0.30;
const EBAY_INTERNATIONAL_FEE = 0.0165;

/**
 * Shopify fee structure (Shopify Payments)
 */
const SHOPIFY_PAYMENT_FEE_PERCENT = 0.029;
const SHOPIFY_PAYMENT_FEE_FIXED = 0.30;

const JPY_TO_USD_RATE = 0.0067;

export function ExportModal({
  isOpen,
  itemCount,
  averagePrice,
  averageShippingCost,
  onConfirm,
  onCancel,
}: ExportModalProps) {
  const [step, setStep] = useState<1 | 2>(1);
  const [selectedPlatform, setSelectedPlatform] = useState<ExportPlatform | null>(null);
  const [desiredMargin, setDesiredMargin] = useState<string>('25');
  const inputRef = useRef<HTMLInputElement>(null);

  // Reset state when modal opens/closes
  useEffect(() => {
    if (isOpen) {
      setStep(1);
      setSelectedPlatform(null);
      setDesiredMargin('25');
    }
  }, [isOpen]);

  // Focus input when step 2 opens
  useEffect(() => {
    if (isOpen && step === 2 && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isOpen, step]);

  // Keyboard handling
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        if (step === 2) {
          setStep(1);
        } else {
          onCancel();
        }
      } else if (e.key === 'Enter' && isOpen && step === 2) {
        handleExportConfirm();
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
  }, [isOpen, step, desiredMargin, selectedPlatform]);

  if (!isOpen) return null;

  const marginPercent = parseFloat(desiredMargin) || 0;
  const avgCostJPY = averagePrice;
  const avgCostUSD = avgCostJPY * JPY_TO_USD_RATE;

  const calculateEBayPricing = () => {
    const totalFeePercent =
      EBAY_FINAL_VALUE_FEE + EBAY_PAYMENT_PROCESSING_PERCENT + EBAY_INTERNATIONAL_FEE;
    const desiredProfit = avgCostUSD * (marginPercent / 100);
    const salePrice =
      (avgCostUSD + averageShippingCost + desiredProfit + EBAY_PAYMENT_PROCESSING_FIXED) /
      (1 - totalFeePercent);
    const finalValueFee = salePrice * EBAY_FINAL_VALUE_FEE;
    const paymentFee = salePrice * EBAY_PAYMENT_PROCESSING_PERCENT + EBAY_PAYMENT_PROCESSING_FIXED;
    const internationalFee = salePrice * EBAY_INTERNATIONAL_FEE;
    const totalFees = finalValueFee + paymentFee + internationalFee;
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

  const calculateShopifyPricing = () => {
    const desiredProfit = avgCostUSD * (marginPercent / 100);

    // For Shopify: shipping is configured in Shopify admin, product price covers cost + margin + fees
    const salePrice =
      (avgCostUSD + desiredProfit + SHOPIFY_PAYMENT_FEE_FIXED) /
      (1 - SHOPIFY_PAYMENT_FEE_PERCENT);
    const paymentFee = salePrice * SHOPIFY_PAYMENT_FEE_PERCENT + SHOPIFY_PAYMENT_FEE_FIXED;

    // Net profit from item sale only
    const netProfit = salePrice - avgCostUSD - paymentFee;
    const actualMargin = (netProfit / avgCostUSD) * 100;

    return {
      salePrice: salePrice.toFixed(2),
      paymentFee: paymentFee.toFixed(2),
      totalFees: paymentFee.toFixed(2),
      netProfit: netProfit.toFixed(2),
      actualMargin: actualMargin.toFixed(1),
      grossMarginPercent: (((salePrice - avgCostUSD) / salePrice) * 100).toFixed(1),
    };
  };

  const handlePlatformSelect = (platform: ExportPlatform) => {
    setSelectedPlatform(platform);
    setStep(2);
  };

  const handleBackToStep1 = () => {
    setStep(1);
  };

  const handleExportConfirm = () => {
    if (!selectedPlatform) return;
    if (marginPercent < 0 || marginPercent > 500) {
      alert('Please enter a margin between 0% and 500%');
      return;
    }
    onConfirm(selectedPlatform, marginPercent);
  };

  const pricing = selectedPlatform === 'ebay' ? calculateEBayPricing() : calculateShopifyPricing();

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="export-dialog-title"
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 transition-opacity"
        onClick={onCancel}
        aria-hidden="true"
      />

      {/* Dialog */}
      <div className="relative z-10 w-full max-w-lg transform rounded-2xl bg-white shadow-2xl transition-all dark:bg-zinc-900">
        {/* Header */}
        <div className="border-b border-zinc-200 px-6 py-4 dark:border-zinc-800">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {step === 2 && (
                <button
                  onClick={handleBackToStep1}
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
                  aria-label="Go back"
                >
                  <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                  </svg>
                </button>
              )}
              <h3 id="export-dialog-title" className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
                {step === 1 ? 'Export Listings' : `Export to ${selectedPlatform === 'ebay' ? 'eBay' : 'Shopify'}`}
              </h3>
            </div>
            <button
              onClick={onCancel}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
              aria-label="Close"
            >
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            {step === 1
              ? `Export ${itemCount} ${itemCount === 1 ? 'listing' : 'listings'} to your preferred platform`
              : 'Configure your pricing strategy'}
          </p>
        </div>

        {/* Content */}
        <div className="px-6 py-5">
          {step === 1 ? (
            /* Step 1: Platform Selection */
            <div className="grid gap-4 sm:grid-cols-2">
              {/* eBay Card */}
              <button
                onClick={() => handlePlatformSelect('ebay')}
                className="group relative flex flex-col items-center rounded-xl border-2 border-zinc-200 p-6 text-left transition hover:border-blue-500 hover:bg-blue-50/50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:border-zinc-700 dark:hover:border-blue-500 dark:hover:bg-blue-900/10"
              >
                <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 shadow-lg">
                  <svg className="h-7 w-7 text-white" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M5.74 5.26c-.16 0-.32.03-.47.07-.2.05-.4.14-.6.26-.2.12-.36.25-.52.4-.3.3-.52.68-.62 1.08-.1.4-.1.83 0 1.22.05.2.14.4.26.6.12.2.25.36.4.52.3.3.68.52 1.08.62.4.1.83.1 1.22 0 .2-.05.4-.14.6-.26.2-.12.36-.25.52-.4.3-.3.52-.68.62-1.08.1-.4.1-.83 0-1.22-.05-.2-.14-.4-.26-.6-.12-.2-.25-.36-.4-.52-.3-.3-.68-.52-1.08-.62-.2-.05-.4-.07-.6-.07h-.15zm12.52 0c-.16 0-.32.03-.47.07-.2.05-.4.14-.6.26-.2.12-.36.25-.52.4-.3.3-.52.68-.62 1.08-.1.4-.1.83 0 1.22.05.2.14.4.26.6.12.2.25.36.4.52.3.3.68.52 1.08.62.4.1.83.1 1.22 0 .2-.05.4-.14.6-.26.2-.12.36-.25.52-.4.3-.3.52-.68.62-1.08.1-.4.1-.83 0-1.22-.05-.2-.14-.4-.26-.6-.12-.2-.25-.36-.4-.52-.3-.3-.68-.52-1.08-.62-.2-.05-.4-.07-.6-.07h-.15zM12 10.5c-2.08 0-3.75 1.67-3.75 3.75S9.92 18 12 18s3.75-1.67 3.75-3.75S14.08 10.5 12 10.5z"/>
                  </svg>
                </div>
                <span className="mt-4 text-base font-semibold text-zinc-900 dark:text-zinc-50">eBay</span>
                <span className="mt-1 text-center text-xs text-zinc-500 dark:text-zinc-400">
                  File Exchange CSV format
                </span>
                <div className="mt-3 flex flex-wrap justify-center gap-1">
                  <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                    13.25% FVF
                  </span>
                  <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                    Global reach
                  </span>
                </div>
              </button>

              {/* Shopify Card */}
              <button
                onClick={() => handlePlatformSelect('shopify')}
                className="group relative flex flex-col items-center rounded-xl border-2 border-zinc-200 p-6 text-left transition hover:border-green-500 hover:bg-green-50/50 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 dark:border-zinc-700 dark:hover:border-green-500 dark:hover:bg-green-900/10"
              >
                <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-gradient-to-br from-green-500 to-green-600 shadow-lg">
                  <svg className="h-7 w-7 text-white" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M15.337 3.415c-.194-.016-.374.104-.434.286l-.707 2.245c-.06.19-.023.397.1.55.06.075.132.135.214.177l-.47 1.49c-.39-.104-.806-.145-1.23-.112-.932.072-1.777.51-2.36 1.186-.584.676-.907 1.554-.907 2.475 0 1.06.422 2.024 1.182 2.71a3.768 3.768 0 002.656.917c.126 0 .255-.007.384-.02.85-.082 1.632-.434 2.254-1.012l.02.025 1.82 5.76c.044.138.145.25.28.31.134.06.285.065.423.014l2.256-.826a.55.55 0 00.347-.65l-2.898-9.177a4.153 4.153 0 00-.15-.39l.494-1.567a.55.55 0 00-.293-.664l-2.14-.932a.549.549 0 00-.64.205zm.19 1.665l1.38.6-.325 1.03-.06-.026a1.62 1.62 0 00-.13-.048l-.866-.287v-1.27zm-3.81 6.54c0-.615.21-1.197.59-1.64.382-.44.91-.73 1.483-.807a2.6 2.6 0 01.898.046l-.99 3.14a2.7 2.7 0 01-1.387-.874 2.558 2.558 0 01-.593-1.866z"/>
                  </svg>
                </div>
                <span className="mt-4 text-base font-semibold text-zinc-900 dark:text-zinc-50">Shopify</span>
                <span className="mt-1 text-center text-xs text-zinc-500 dark:text-zinc-400">
                  Product import CSV
                </span>
                <div className="mt-3 flex flex-wrap justify-center gap-1">
                  <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                    2.9% + $0.30
                  </span>
                  <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                    Own store
                  </span>
                </div>
              </button>
            </div>
          ) : (
            /* Step 2: Pricing Configuration */
            <div>
              {/* Margin Input */}
              <div>
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
                <p className="mt-1 text-xs text-zinc-500">
                  {selectedPlatform === 'shopify'
                    ? 'Net profit margin on item sale'
                    : 'Net profit margin after all fees and shipping costs'}
                </p>
              </div>

              {/* Pricing Breakdown */}
              <div className="mt-5 rounded-xl bg-zinc-50 p-4 dark:bg-zinc-800/50">
                <h4 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                  Pricing Breakdown (Average per item)
                </h4>
                <div className="mt-3 space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-zinc-600 dark:text-zinc-400">Cost (¥{avgCostJPY.toLocaleString()})</span>
                    <span className="font-medium text-zinc-900 dark:text-zinc-50">${avgCostUSD.toFixed(2)}</span>
                  </div>
                  {selectedPlatform === 'ebay' && (
                    <div className="flex justify-between">
                      <span className="text-zinc-600 dark:text-zinc-400">Shipping (included in price)</span>
                      <span className="font-medium text-zinc-900 dark:text-zinc-50">${averageShippingCost.toFixed(2)}</span>
                    </div>
                  )}
                  <div className="flex justify-between border-t border-zinc-200 pt-2 dark:border-zinc-700">
                    <span className="font-medium text-zinc-700 dark:text-zinc-300">
                      {selectedPlatform === 'shopify' ? 'Product Price' : 'Sale Price'}
                    </span>
                    <span className={`font-semibold ${selectedPlatform === 'ebay' ? 'text-blue-600 dark:text-blue-400' : 'text-green-600 dark:text-green-400'}`}>
                      ${pricing.salePrice}
                    </span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-zinc-500">Gross Margin: {pricing.grossMarginPercent}%</span>
                  </div>
                </div>

                {/* Platform-specific Fees */}
                <div className="mt-4 border-t border-zinc-200 pt-3 dark:border-zinc-700">
                  <h5 className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
                    {selectedPlatform === 'ebay' ? 'eBay Fees' : 'Shopify Fees'}
                  </h5>
                  <div className="mt-2 space-y-1 text-xs">
                    {selectedPlatform === 'ebay' ? (
                      <>
                        <div className="flex justify-between text-zinc-600 dark:text-zinc-400">
                          <span>Final Value Fee (13.25%)</span>
                          <span>${(pricing as ReturnType<typeof calculateEBayPricing>).finalValueFee}</span>
                        </div>
                        <div className="flex justify-between text-zinc-600 dark:text-zinc-400">
                          <span>Payment Processing (2.35% + $0.30)</span>
                          <span>${pricing.paymentFee}</span>
                        </div>
                        <div className="flex justify-between text-zinc-600 dark:text-zinc-400">
                          <span>International Fee (1.65%)</span>
                          <span>${(pricing as ReturnType<typeof calculateEBayPricing>).internationalFee}</span>
                        </div>
                      </>
                    ) : (
                      <div className="flex justify-between text-zinc-600 dark:text-zinc-400">
                        <span>Payment Processing (2.9% + $0.30)</span>
                        <span>${pricing.paymentFee}</span>
                      </div>
                    )}
                    <div className="flex justify-between border-t border-zinc-200 pt-1 font-medium dark:border-zinc-700">
                      <span className="text-zinc-700 dark:text-zinc-300">Total Fees</span>
                      <span className="text-red-600 dark:text-red-400">-${pricing.totalFees}</span>
                    </div>
                  </div>
                </div>

                {/* Net Profit */}
                <div className="mt-4 rounded-lg bg-green-50 p-3 dark:bg-green-900/20">
                  <div className="flex justify-between">
                    <span className="font-semibold text-green-900 dark:text-green-100">Net Profit per Item</span>
                    <span className="text-lg font-bold text-green-600 dark:text-green-400">${pricing.netProfit}</span>
                  </div>
                  <div className="mt-1 flex justify-between text-xs">
                    <span className="text-green-700 dark:text-green-300">Net Margin</span>
                    <span className="font-semibold text-green-700 dark:text-green-300">{pricing.actualMargin}%</span>
                  </div>
                </div>

                {itemCount > 1 && (
                  <div className="mt-3 text-xs text-zinc-600 dark:text-zinc-400">
                    Total net profit for {itemCount} items: ${(parseFloat(pricing.netProfit) * itemCount).toFixed(2)}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        {step === 2 && (
          <div className="border-t border-zinc-200 px-6 py-4 dark:border-zinc-800">
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={onCancel}
                className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-semibold text-zinc-700 transition hover:bg-zinc-50 focus:outline-none focus:ring-2 focus:ring-zinc-500 focus:ring-offset-2 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleExportConfirm}
                className={`rounded-lg px-4 py-2 text-sm font-semibold text-white transition focus:outline-none focus:ring-2 focus:ring-offset-2 ${
                  selectedPlatform === 'ebay'
                    ? 'bg-blue-600 hover:bg-blue-700 focus:ring-blue-500 dark:bg-blue-500 dark:hover:bg-blue-600'
                    : 'bg-green-600 hover:bg-green-700 focus:ring-green-500 dark:bg-green-500 dark:hover:bg-green-600'
                }`}
              >
                Export to {selectedPlatform === 'ebay' ? 'eBay' : 'Shopify'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
