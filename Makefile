CC = clang
CFLAGS = -Wall -Wextra -I./src
SRC_DIR = src
OBJ_DIR = obj

SRCS = $(wildcard $(SRC_DIR)/*.c)
OBJS = $(SRCS:$(SRC_DIR)/%.c=$(OBJ_DIR)/%.o)
TARGET = program

.PHONY: all clean compile_commands.json

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(OBJS) -o $(TARGET)

$(OBJ_DIR)/%.o: $(SRC_DIR)/%.c
	@mkdir -p $(OBJ_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

compile_commands.json:
	@echo "Generating compile_commands.json..."
	@echo "[" > compile_commands.json
	@for file in $(SRCS); do \
		echo "  {" >> compile_commands.json; \
		echo "    \"directory\": \"$(shell pwd)\"," >> compile_commands.json; \
		echo "    \"command\": \"$(CC) $(CFLAGS) -c $$file -o $(OBJ_DIR)/$$(basename $$file .c).o\"," >> compile_commands.json; \
		echo "    \"file\": \"$$file\"" >> compile_commands.json; \
		echo "  }," >> compile_commands.json; \
	done
	@sed -i '$$d' compile_commands.json
	@echo "  }" >> compile_commands.json
	@echo "]" >> compile_commands.json

clean:
	rm -rf $(OBJ_DIR) $(TARGET) compile_commands.json 