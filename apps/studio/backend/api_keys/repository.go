package api_keys

import (
	"context"
	"junjo-server/db"
	"junjo-server/db_gen"
)

// CreateAPIKey inserts a new API key into the database.
func CreateAPIKey(ctx context.Context, id string, key string, name string) (db_gen.ApiKey, error) {
	queries := db_gen.New(db.DB)
	apiKey, err := queries.CreateAPIKey(ctx, db_gen.CreateAPIKeyParams{
		ID:   id,
		Key:  key,
		Name: name,
	})
	if err != nil {
		return db_gen.ApiKey{}, err
	}
	return apiKey, nil
}

// GetAPIKey retrieves a single API key by its key value.
func GetAPIKey(ctx context.Context, key string) (db_gen.ApiKey, error) {
	queries := db_gen.New(db.DB)
	apiKey, err := queries.GetAPIKey(ctx, key)
	if err != nil {
		return db_gen.ApiKey{}, err
	}
	return apiKey, nil
}

// ListAPIKeys retrieves all API keys, ordered by creation date descending.
func ListAPIKeys(ctx context.Context) ([]db_gen.ApiKey, error) {
	queries := db_gen.New(db.DB)
	apiKeys, err := queries.ListAPIKeys(ctx)
	if err != nil {
		return nil, err
	}
	return apiKeys, nil
}

// DeleteAPIKey removes an API key from the database by its key value.
func DeleteAPIKey(ctx context.Context, key string) error {
	queries := db_gen.New(db.DB)
	err := queries.DeleteAPIKey(ctx, key)
	if err != nil {
		return err
	}
	return nil
}
