import { argon2id } from 'hash-wasm'

const LEGACY_FIO_TOKEN_KEY = 'fio_token'
const SESSION_VAULT_PASSWORD_KEY = 'vault_password_session'
const LOCAL_VAULT_PASSWORD_KEY = 'vault_password_local'

export interface EncryptedSecretPayload {
  ciphertext: string
  nonce: string
  salt: string
  kdf: 'argon2id'
  kdf_params: {
    iterations: number
    memorySize: number
    parallelism: number
    hashLength: number
  }
}

const DEFAULT_KDF_PARAMS = {
  iterations: 3,
  memorySize: 65536,
  parallelism: 1,
  hashLength: 32,
}

const textEncoder = new TextEncoder()
const textDecoder = new TextDecoder()

function toBase64(bytes: Uint8Array): string {
  let binary = ''
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte)
  })
  return btoa(binary)
}

function fromBase64(value: string): Uint8Array {
  const binary = atob(value)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  return bytes
}

async function deriveAesKey(password: string, salt: Uint8Array, params = DEFAULT_KDF_PARAMS) {
  const keyBytes = await argon2id({
    password,
    salt,
    iterations: params.iterations,
    memorySize: params.memorySize,
    parallelism: params.parallelism,
    hashLength: params.hashLength,
    outputType: 'binary',
  })
  const normalizedKeyBytes = new Uint8Array(keyBytes)

  return window.crypto.subtle.importKey(
    'raw',
    normalizedKeyBytes as BufferSource,
    { name: 'AES-GCM' },
    false,
    ['encrypt', 'decrypt']
  )
}

export async function encryptSecret(secret: string, password: string): Promise<EncryptedSecretPayload> {
  const salt = window.crypto.getRandomValues(new Uint8Array(16))
  const nonce = window.crypto.getRandomValues(new Uint8Array(12))
  const key = await deriveAesKey(password, salt)
  const ciphertext = await window.crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: nonce },
    key,
    textEncoder.encode(secret)
  )

  return {
    ciphertext: toBase64(new Uint8Array(ciphertext)),
    nonce: toBase64(nonce),
    salt: toBase64(salt),
    kdf: 'argon2id',
    kdf_params: DEFAULT_KDF_PARAMS,
  }
}

export async function decryptSecret(payload: EncryptedSecretPayload, password: string): Promise<string> {
  const salt = fromBase64(payload.salt)
  const nonce = fromBase64(payload.nonce)
  const ciphertext = fromBase64(payload.ciphertext)
  const key = await deriveAesKey(password, salt, payload.kdf_params)

  try {
    const plaintext = await window.crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: nonce as BufferSource },
      key,
      ciphertext as BufferSource
    )
    return textDecoder.decode(plaintext)
  } catch {
    throw new Error('Vault password is incorrect')
  }
}

export function getRememberedVaultPassword(): string | null {
  return localStorage.getItem(LOCAL_VAULT_PASSWORD_KEY) || sessionStorage.getItem(SESSION_VAULT_PASSWORD_KEY)
}

export function hasPersistentVaultPassword(): boolean {
  return !!localStorage.getItem(LOCAL_VAULT_PASSWORD_KEY)
}

export function rememberVaultPassword(password: string, persistOnDevice: boolean) {
  sessionStorage.setItem(SESSION_VAULT_PASSWORD_KEY, password)
  if (persistOnDevice) {
    localStorage.setItem(LOCAL_VAULT_PASSWORD_KEY, password)
  } else {
    localStorage.removeItem(LOCAL_VAULT_PASSWORD_KEY)
  }
}

export function clearRememberedVaultPassword() {
  sessionStorage.removeItem(SESSION_VAULT_PASSWORD_KEY)
  localStorage.removeItem(LOCAL_VAULT_PASSWORD_KEY)
}

export function getLegacyFioToken(): string | null {
  return localStorage.getItem(LEGACY_FIO_TOKEN_KEY)
}

export function clearLegacyFioToken() {
  localStorage.removeItem(LEGACY_FIO_TOKEN_KEY)
}

export async function unlockStoredSecret(payload: EncryptedSecretPayload): Promise<string> {
  const remembered = getRememberedVaultPassword()
  if (remembered) {
    try {
      const secret = await decryptSecret(payload, remembered)
      rememberVaultPassword(remembered, hasPersistentVaultPassword())
      return secret
    } catch {
      clearRememberedVaultPassword()
    }
  }

  const prompted = window.prompt('Enter your vault password to decrypt the Fio token')
  if (!prompted) {
    throw new Error('Vault password is required')
  }

  const secret = await decryptSecret(payload, prompted)
  rememberVaultPassword(prompted, false)
  return secret
}
