import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { OrderResult } from "../types/api";

export interface ChatOrderContextValue {
  orderId: string | null;
  orderResult: OrderResult | null;
  setActiveOrder: (order: OrderResult | null) => void;
  clearActiveOrder: () => void;
}

const ChatOrderContext = createContext<ChatOrderContextValue | null>(null);

export function ChatOrderProvider({ children }: { children: ReactNode }) {
  const [orderResult, setOrderResult] = useState<OrderResult | null>(null);

  const setActiveOrder = useCallback((order: OrderResult | null) => {
    setOrderResult(order);
  }, []);

  const clearActiveOrder = useCallback(() => {
    setOrderResult(null);
  }, []);

  const value = useMemo<ChatOrderContextValue>(
    () => ({
      orderId: orderResult?.order_id ?? null,
      orderResult,
      setActiveOrder,
      clearActiveOrder,
    }),
    [orderResult, setActiveOrder, clearActiveOrder],
  );

  return <ChatOrderContext.Provider value={value}>{children}</ChatOrderContext.Provider>;
}

const FALLBACK_CHAT_ORDER: ChatOrderContextValue = {
  orderId: null,
  orderResult: null,
  setActiveOrder: () => {},
  clearActiveOrder: () => {},
};

export function useChatOrder(): ChatOrderContextValue {
  return useContext(ChatOrderContext) ?? FALLBACK_CHAT_ORDER;
}
