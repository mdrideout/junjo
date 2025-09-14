package jwks

import (
	"crypto/rsa"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"math/big"
	"net/http"
	"sync"
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
		// Perform an initial fetch.
		if err := keySet.fetchKeys(); err != nil {
			// In a real application, you might want to handle this more gracefully.
			// For now, we'll just log the error.
			fmt.Printf("Initial JWKS fetch failed: %v\n", err)
		}
	})
}

// fetchKeys fetches the JWKS from the backend and replaces the existing KeySet.
func (ks *KeySet) fetchKeys() error {
	resp, err := http.Get("http://junjo-server-backend:1323/.well-known/jwks.json")
	if err != nil {
		return fmt.Errorf("error fetching JWKS: %w", err)
	}
	defer resp.Body.Close()

	var jwks JWKS
	if err := json.NewDecoder(resp.Body).Decode(&jwks); err != nil {
		return fmt.Errorf("error decoding JWKS: %w", err)
	}

	newKeys := make(map[string]*rsa.PublicKey)
	for _, key := range jwks.Keys {
		n, err := base64.RawURLEncoding.DecodeString(key.N)
		if err != nil {
			// Log the error but continue processing other keys.
			fmt.Printf("Error decoding N for key %s: %v\n", key.Kid, err)
			continue
		}
		e, err := base64.RawURLEncoding.DecodeString(key.E)
		if err != nil {
			// Log the error but continue processing other keys.
			fmt.Printf("Error decoding E for key %s: %v\n", key.Kid, err)
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
		return nil, fmt.Errorf("error refetching JWKS: %w", err)
	}

	// After refetching, check for the key one last time.
	key, ok = keySet.keys[kid]
	if !ok {
		return nil, fmt.Errorf("key not found after refetch")
	}

	return key, nil
}
