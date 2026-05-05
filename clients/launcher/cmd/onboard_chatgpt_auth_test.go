package cmd

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestArchiveChatGPTAuthFile(t *testing.T) {
	tokenDir := t.TempDir()
	authPath := filepath.Join(tokenDir, "auth.json")
	if err := os.WriteFile(authPath, []byte(`{"access_token":"stale"}`), 0o600); err != nil {
		t.Fatalf("write auth file: %v", err)
	}

	archived, err := archiveChatGPTAuthFile(
		tokenDir,
		time.Date(2026, 5, 5, 12, 34, 56, 0, time.UTC),
	)
	if err != nil {
		t.Fatalf("archiveChatGPTAuthFile() error = %v", err)
	}
	want := filepath.Join(tokenDir, "auth.json.invalidated.20260505-123456")
	if archived != want {
		t.Fatalf("archived path = %q, want %q", archived, want)
	}
	if _, err := os.Stat(authPath); !os.IsNotExist(err) {
		t.Fatalf("auth.json should be moved, stat err = %v", err)
	}
	if _, err := os.Stat(want); err != nil {
		t.Fatalf("archived auth file missing: %v", err)
	}
}

func TestArchiveChatGPTAuthFileMissingIsNoop(t *testing.T) {
	archived, err := archiveChatGPTAuthFile(t.TempDir(), time.Now())
	if err != nil {
		t.Fatalf("archiveChatGPTAuthFile() error = %v", err)
	}
	if archived != "" {
		t.Fatalf("archived path = %q, want empty", archived)
	}
}
