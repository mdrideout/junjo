package jwks

import (
	"crypto/rsa"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log/slog"
	"math/big"
	"net/http"
	"sync"
	"time"
)

// JWK represents a JSON Web Key.
type JWK struct {
	Kty string `json:"kty"`
	Kid string `json:"kid"`
	Use string `json:"use"`
	N   string `json:"n"`
	E   string `json:"e"`
}

// JWKS represents a JSON Web Key Set.
type JWKS struct {
	Keys []JWK `json:"keys"`
}

// KeySet holds the public keys fetched from the JWKS endpoint.
type KeySet struct {
	keys map[string]*rsa.PublicKey
	mu   sync.RWMutex
}

var (
	keySet *KeySet
	once   sync.Once
)

// Init initializes the KeySet.
func Init() {
	once.Do(func() {
		keySet = &KeySet{
			keys: make(map[string]*rsa.PublicKey),
		}
		// We don't block startup on this fetch. Instead, we retry in the background.
		go func() {
			for {
				err := keySet.fetchKeys()
				if err == nil {
					slog.Info("Initial JWKS fetch succeeded")
					return // Exit goroutine on success
				}
				slog.Error("Initial JWKS fetch failed, retrying in 5 seconds...", "error", err)
				time.Sleep(5 * time.Second)
			}
		}()
	})
}

// fetchKeys fetches the JWKS from the backend and replaces the existing KeySet.
func (ks *KeySet) fetchKeys() error {
	slog.Info("Attempting to fetch JWKS from backend...")
	resp, err := http.Get("http://junjo-server-backend:1323/.well-known/jwks.json")
	if err != nil {
		return fmt.Errorf("error fetching JWKS: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("failed to fetch JWKS: received status code %d", resp.StatusCode)
	}

	var jwks JWKS
	if err := json.NewDecoder(resp.Body).Decode(&jwks); err != nil {
		return fmt.Errorf("error decoding JWKS: %w", err)
	}

	newKeys := make(map[string]*rsa.PublicKey)
	for _, key := range jwks.Keys {
		n, err := base64.RawURLEncoding.DecodeString(key.N)
		if err != nil {
			// Log the error but continue processing other keys.
			slog.Error("Error decoding N for key", "kid", key.Kid, "error", err)
			continue
		}
		e, err := base64.RawURLEncoding.DecodeString(key.E)
		if err != nil {
			// Log the error but continue processing other keys.
			slog.Error("Error decoding E for key", "kid", key.Kid, "error", err)
			continue
		}
		newKeys[key.Kid] = &rsa.PublicKey{
			N: new(big.Int).SetBytes(n),
			E: int(new(big.Int).SetBytes(e).Int64()),
		}
	}

	ks.mu.Lock()
	ks.keys = newKeys
	ks.mu.Unlock()

	return nil
}

// GetKey returns the public key for the given key ID.
func GetKey(kid string) (*rsa.PublicKey, error) {
	// First, check for the key with a read lock.
	keySet.mu.RLock()
	key, ok := keySet.keys[kid]
	keySet.mu.RUnlock()

	if ok {
		return key, nil
	}

	// If the key is not found, acquire a write lock to refetch.
	keySet.mu.Lock()
	defer keySet.mu.Unlock()

	// Double-check if the key was fetched by another goroutine
	// while we were waiting for the write lock.
	key, ok = keySet.keys[kid]
	if ok {
		return key, nil
	}

	// If the key is still not found, refetch the JWKS.
	if err := keySet.fetchKeys(); err != nil {
		slog.Error("Error refetching JWKS", "error", err)
		return nil, fmt.Errorf("error refetching JWKS: %w", err)
	}

	// After refetching, check for the key one last time.
	key, ok = keySet.keys[kid]
	if !ok {
		slog.Error("Key not found after JWKS refetch", "kid", kid)
		return nil, fmt.Errorf("key not found after refetch")
	}

	return key, nil
}
