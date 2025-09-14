package jwks

import (
	"crypto/rand"
	"crypto/rsa"
	"encoding/base64"
	"math/big"
	"net/http"
	"sync"

	"github.com/labstack/echo/v4"
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

var (
	privateKey *rsa.PrivateKey
	publicKey  *rsa.PublicKey
	jwks       *JWKS
	once       sync.Once
)

// generateKeys generates a new RSA key pair and JWKS.
func generateKeys() {
	var err error
	privateKey, err = rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		panic(err)
	}
	publicKey = &privateKey.PublicKey

	jwks = &JWKS{
		Keys: []JWK{
			{
				Kty: "RSA",
				Kid: "1",
				Use: "sig",
				N:   base64.RawURLEncoding.EncodeToString(publicKey.N.Bytes()),
				E:   base64.RawURLEncoding.EncodeToString(big.NewInt(int64(publicKey.E)).Bytes()),
			},
		},
	}
}

// Init initializes the JWKS endpoint.
// It generates an RSA key pair and a JWKS on the first call.
func Init() {
	once.Do(generateKeys)
}

// HandleJWKSRequest handles requests for the JWKS.
// It returns the JWKS as a JSON response.
func HandleJWKSRequest(c echo.Context) error {
	return c.JSON(http.StatusOK, jwks)
}

// GetPrivateKey returns the RSA private key.
// This is used by the OTel token service to sign JWTs.
func GetPrivateKey() *rsa.PrivateKey {
	return privateKey
}
