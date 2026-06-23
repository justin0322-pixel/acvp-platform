export type Envelope<T> = [{ acvVersion: string }, T];

export interface LoginResult {
  accessToken: string;
  largeEndpointRequired: boolean;
  sizeConstraint: number;
}

export interface Algorithm {
  algorithm: string;
  mode: string;
  revision: string;
}
