import "@stdlib/deploy";

const OP_TRANSFER = 0x5fcc3d14;

var collection_address: address;
var index: int;
var owner: address;
var content: cell;

fun init(collection: address, idx: int, initial_owner: address, nft_content: cell) {
    self.collection_address = collection;
    self.index = idx;
    self.owner = initial_owner;
    self.content = nft_content;
}

fun receive(msg: Message) {
    if (msg.op == OP_TRANSFER) {
        require(msg.sender == self.owner, "Only owner can transfer");
        self.owner = msg.new_owner;
    }
}

fun get_owner(): address {
    return self.owner;
}
