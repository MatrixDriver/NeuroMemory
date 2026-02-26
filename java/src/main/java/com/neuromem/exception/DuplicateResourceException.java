package com.neuromem.exception;

/**
 * Exception thrown when attempting to create a resource that already exists.
 */
public class DuplicateResourceException extends RuntimeException {

    public DuplicateResourceException(String message) {
        super(message);
    }

    public DuplicateResourceException(String resource, String identifier) {
        super(String.format("%s with identifier '%s' already exists", resource, identifier));
    }
}
