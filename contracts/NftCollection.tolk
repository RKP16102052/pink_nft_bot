import "@stdlib/deploy";

const OP_MINT = 0x6d696e74;

var owner_address: address;
var next_item_index: int = 0;
var items: dict<int, address>;

fun init(owner: address) {
    self.owner_address = owner;
    self.items = empty_dict();
}

fun receive(msg: Message) {
    if (msg.op == OP_MINT) {
        require(msg.sender == self.owner_address, "Only owner can mint");
        
        let index = self.next_item_index;
        let content = msg.body.load_ref();
        
        let nft_address = deploy_contract(
            "NftItem",
            self.address,
            index,
            msg.sender,
            content
        );
        
        self.items[index] = nft_address;
        self.next_item_index = index + 1;
    }
}

fun get_nft_address(index: int): address {
    return self.items[index];
}
