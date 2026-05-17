export type ChatMsg = {
  role: 'user' | 'assistant' | 'error';
  text: string;
  streaming?: boolean;
  interrupted?: boolean;
};
